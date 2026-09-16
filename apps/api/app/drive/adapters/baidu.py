"""百度网盘官方接口。个人应用一般只能进 /apps/应用名/。"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.drive.paths import crumbs, entry_of, join_path, normalize_path

_AUTH = "https://openapi.baidu.com/oauth/2.0"
_XPAN = "https://pan.baidu.com/rest/2.0/xpan"
_UPLOAD = "https://d.pcs.baidu.com/rest/2.0/pcs/superfile2"
_CHUNK = 4 * 1024 * 1024
_UA = "pan.baidu.com"

_ERRNO = {
    -6: "授权失效，请重新授权",
    -7: "文件或目录名不合法",
    -9: "文件不存在",
    -10: "网盘空间不足，请先删文件或开通会员后再上传",
    2: "参数不对",
    111: "授权过期，请重新授权",
    31023: "参数不对",
    31034: "请求太勤，请稍后再试",
    31045: "授权失败，请重新授权",
    31061: "文件已存在",
    31066: "文件不存在",
    31112: "网盘空间不足，请先删文件或开通会员后再上传",
    31299: "只能访问应用目录，请把应用名称填成开放平台上的应用名",
    31326: "命中反作弊，请稍后再试",
    42213: "没有权限访问这个目录",
}


def _size_text(n: int) -> str:
    value = float(max(n, 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)}B"
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{int(n)}B"


def _thumb_url(row: dict[str, Any]) -> str:
    thumbs = row.get("thumbs")
    if not isinstance(thumbs, dict):
        return ""
    return str(thumbs.get("url2") or thumbs.get("url1") or thumbs.get("url3") or "")


def _msg(errno: int, fallback: str = "") -> str:
    if errno == 0:
        return ""
    return _ERRNO.get(errno) or fallback or f"百度返回错误 {errno}"


class BaiduAdapter:
    """百度网盘：授权、列目录、上传下载、改名删除。"""

    def default_root(self, account: dict[str, Any]) -> str:
        name = str(account.get("app_name") or "").strip().strip("/")
        return f"/apps/{name}" if name else "/"

    def start_auth(self, account: dict[str, Any]) -> dict[str, Any]:
        app_key = str(account.get("app_key") or "").strip()
        if not app_key:
            raise ValueError("请先填 AppKey")
        data = self._json(
            "GET",
            f"{_AUTH}/device/code",
            params={"client_id": app_key, "response_type": "device_code", "scope": "basic,netdisk"},
        )
        if data.get("error"):
            raise ValueError(self._oauth_error(data))
        user_code = str(data.get("user_code") or "")
        verify = str(data.get("verification_url") or "https://openapi.baidu.com/device")
        if not user_code:
            raise ValueError("百度没返回授权码，请检查 AppKey")
        return {
            "device_code": str(data.get("device_code") or ""),
            "user_code": user_code,
            "verify_url": verify,
            "qrcode_url": str(data.get("qrcode_url") or ""),
            "interval": int(data.get("interval") or 5),
            "auth_url": self.auth_url(account),
        }

    def auth_url(self, account: dict[str, Any], redirect_uri: str = "") -> str:
        app_key = quote(str(account.get("app_key") or "").strip(), safe="")
        redirect = quote(redirect_uri or "oob", safe="")
        state = quote(str(account.get("id") or ""), safe="")
        return (
            f"{_AUTH}/authorize?response_type=code&client_id={app_key}"
            f"&redirect_uri={redirect}&scope=basic,netdisk&display=page&state={state}"
        )

    def poll_auth(self, account: dict[str, Any], device_code: str) -> dict[str, Any] | None:
        data = self._json(
            "GET",
            f"{_AUTH}/token",
            params={
                "grant_type": "device_token",
                "code": device_code,
                "client_id": str(account.get("app_key") or "").strip(),
                "client_secret": str(account.get("secret_key") or "").strip(),
            },
        )
        err = str(data.get("error") or "")
        if err in {"authorization_pending", "slow_down"}:
            return None
        if err:
            raise ValueError(self._oauth_error(data))
        return self._tokens_from(data)

    def finish_code(self, account: dict[str, Any], code: str, redirect_uri: str) -> dict[str, Any]:
        data = self._json(
            "GET",
            f"{_AUTH}/token",
            params={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": str(account.get("app_key") or "").strip(),
                "client_secret": str(account.get("secret_key") or "").strip(),
                "redirect_uri": redirect_uri,
            },
        )
        if data.get("error"):
            raise ValueError(self._oauth_error(data))
        return self._tokens_from(data)

    def refresh(self, account: dict[str, Any]) -> dict[str, Any]:
        refresh_token = str(account.get("refresh_token") or "").strip()
        if not refresh_token:
            raise ValueError("授权失效，请重新授权")
        data = self._json(
            "GET",
            f"{_AUTH}/token",
            params={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": str(account.get("app_key") or "").strip(),
                "client_secret": str(account.get("secret_key") or "").strip(),
            },
        )
        if data.get("error"):
            raise ValueError(self._oauth_error(data))
        return self._tokens_from(data)

    def user_label(self, account: dict[str, Any]) -> str:
        data = self._xpan("GET", "/nas", {"method": "uinfo"}, account)
        return str(data.get("netdisk_name") or data.get("baidu_name") or "")

    def list_dir(self, account: dict[str, Any], path: str) -> dict[str, Any]:
        folder = normalize_path(path) if path else self.default_root(account)
        items: list[dict] = []
        start = 0
        while True:
            data = self._xpan(
                "GET",
                "/file",
                {"method": "list", "dir": folder, "start": start, "limit": 200, "order": "name", "web": "1"},
                account,
            )
            rows = data.get("list") if isinstance(data.get("list"), list) else []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                items.append(
                    entry_of(
                        str(row.get("server_filename") or ""),
                        str(row.get("path") or ""),
                        int(row.get("isdir") or 0) == 1,
                        int(row.get("size") or 0),
                        int(row.get("server_mtime") or row.get("local_mtime") or 0),
                        int(row.get("fs_id") or 0),
                        _thumb_url(row),
                    )
                )
            if len(rows) < 200:
                break
            start += 200
        return {"root": self.default_root(account), "path": folder, "crumbs": crumbs(folder), "items": items}

    def search(self, account: dict[str, Any], query: str, path: str) -> dict[str, Any]:
        folder = normalize_path(path) if path else self.default_root(account)
        data = self._xpan(
            "GET",
            "/file",
            {"method": "search", "key": query.strip(), "dir": folder, "recursion": 1, "num": 100, "web": "1"},
            account,
        )
        items = []
        rows = data.get("list") if isinstance(data.get("list"), list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            items.append(
                entry_of(
                    str(row.get("server_filename") or ""),
                    str(row.get("path") or ""),
                    int(row.get("isdir") or 0) == 1,
                    int(row.get("size") or 0),
                    int(row.get("server_mtime") or 0),
                    int(row.get("fs_id") or 0),
                    _thumb_url(row),
                )
            )
        return {"root": self.default_root(account), "path": folder, "crumbs": crumbs(folder), "items": items}

    def quota(self, account: dict[str, Any]) -> dict[str, Any]:
        """查已用空间和总容量，给页面展示。"""
        empty = {
            "total": 0,
            "used": 0,
            "remain": 0,
            "over": False,
            "total_text": "",
            "used_text": "",
            "remain_text": "",
            "message": "",
        }
        try:
            info = self._json(
                "GET",
                "https://pan.baidu.com/api/quota",
                params={"access_token": self._token(account), "checkfree": 1, "checkexpire": 1},
            )
        except ValueError:
            return empty
        errno = int(info.get("errno") or 0)
        if errno in {111, -6, 31045} and account.get("refresh_token"):
            try:
                tokens = self.refresh(account)
                account.update(tokens)
                info = self._json(
                    "GET",
                    "https://pan.baidu.com/api/quota",
                    params={"access_token": tokens["access_token"], "checkfree": 1, "checkexpire": 1},
                )
                errno = int(info.get("errno") or 0)
            except ValueError:
                return empty
        if errno != 0:
            return empty
        total = int(info.get("total") or 0)
        used = int(info.get("used") or 0)
        remain = max(0, total - used)
        over = bool(total and used >= total)
        return {
            "total": total,
            "used": used,
            "remain": remain,
            "over": over,
            "total_text": _size_text(total),
            "used_text": _size_text(used),
            "remain_text": _size_text(remain),
            "message": "网盘空间不足，请先删文件或开通会员后再上传" if over else "",
        }

    def mkdir(self, account: dict[str, Any], path: str, name: str) -> dict[str, Any]:
        dest = join_path(path or self.default_root(account), name)
        self._xpan("POST", "/file", {"method": "create"}, account, data={"path": dest, "isdir": 1, "rtype": 1})
        return entry_of(name, dest, True)

    def rename(self, account: dict[str, Any], path: str, name: str) -> dict[str, Any]:
        src = normalize_path(path)
        new_name = name.strip()
        if not new_name or "/" in new_name or "\\" in new_name:
            raise ValueError("名字不合法")
        self._manager(account, "rename", [{"path": src, "newname": new_name}])
        parent = src.rsplit("/", 1)[0] or "/"
        return entry_of(new_name, join_path(parent, new_name), False)

    def move(self, account: dict[str, Any], path: str, dest: str) -> dict[str, Any]:
        return self.relocate(account, [path], dest, "move")[0]

    def copy(self, account: dict[str, Any], path: str, dest: str) -> dict[str, Any]:
        return self.relocate(account, [path], dest, "copy")[0]

    def relocate(self, account: dict[str, Any], paths: list[str], dest: str, opera: str) -> list[dict[str, Any]]:
        folder = normalize_path(dest or self.default_root(account))
        rows: list[dict[str, Any]] = []
        created: list[dict[str, Any]] = []
        for raw in paths:
            src = normalize_path(raw)
            name = src.rsplit("/", 1)[-1]
            if opera == "move" and (folder == src or folder.startswith(src.rstrip("/") + "/")):
                raise ValueError("不能移到自己里面")
            rows.append({"path": src, "dest": folder, "newname": name})
            created.append(entry_of(name, join_path(folder, name), False))
        if not rows:
            raise ValueError("请先选文件")
        self._manager(account, opera, rows)
        return created

    def delete(self, account: dict[str, Any], path: str) -> None:
        self.delete_many(account, [path])

    def delete_many(self, account: dict[str, Any], paths: list[str]) -> None:
        items = [normalize_path(item) for item in paths if str(item).strip()]
        if not items:
            raise ValueError("请先选文件")
        self._manager(account, "delete", items)

    def upload(self, account: dict[str, Any], path: str, filename: str, file_path: str) -> dict[str, Any]:
        source = Path(file_path)
        size = source.stat().st_size if source.exists() else 0
        if size <= 0:
            raise ValueError("不能上传空文件")
        self._assert_quota(account, size)
        dest = self._upload_dest(account, path, filename)
        self._ensure_dir(account, dest.rsplit("/", 1)[0] or "/")
        md5s: list[str] = []
        whole = hashlib.md5()
        first_slice = hashlib.md5()
        with source.open("rb") as handle:
            first = True
            while True:
                chunk = handle.read(_CHUNK)
                if not chunk:
                    break
                md5s.append(hashlib.md5(chunk).hexdigest())
                whole.update(chunk)
                if first:
                    first_slice.update(chunk[: 256 * 1024])
                    first = False
        body = {
            "path": dest,
            "size": str(size),
            "isdir": "0",
            "autoinit": "1",
            "rtype": "1",
            "block_list": json.dumps(md5s, ensure_ascii=False),
            "content-md5": whole.hexdigest(),
            "slice-md5": first_slice.hexdigest(),
        }
        pre = self._xpan("POST", "/file", {"method": "precreate", "openapi": "xpansdk"}, account, data=body)
        if int(pre.get("return_type") or 0) == 2:
            return entry_of(Path(dest).name, dest, False, size, fsid=int(pre.get("fs_id") or 0))
        upload_id = str(pre.get("uploadid") or "")
        if not upload_id:
            raise ValueError("百度没给上传号")
        token = self._token(account)
        pending = pre.get("block_list")
        if isinstance(pending, list) and pending and all(str(item).isdigit() for item in pending):
            need = {int(item) for item in pending}
        else:
            need = set(range(len(md5s)))
        with source.open("rb") as handle:
            for index in range(len(md5s)):
                chunk = handle.read(_CHUNK)
                if need and index not in need:
                    continue
                with httpx.Client(timeout=600) as client:
                    res = client.post(
                        _UPLOAD,
                        params={
                            "method": "upload",
                            "access_token": token,
                            "type": "tmpfile",
                            "path": dest,
                            "uploadid": upload_id,
                            "partseq": str(index),
                        },
                        headers={"User-Agent": _UA},
                        files={"file": ("blob", chunk, "application/octet-stream")},
                    )
                part = self._as_json(res)
                if int(part.get("errno") or 0) != 0 and "md5" not in part:
                    raise ValueError(_msg(int(part.get("errno") or 0), "分片上传失败"))
        created = self._xpan(
            "POST",
            "/file",
            {"method": "create", "openapi": "xpansdk"},
            account,
            data={
                "path": dest,
                "size": str(size),
                "isdir": "0",
                "rtype": "1",
                "uploadid": upload_id,
                "block_list": json.dumps(md5s, ensure_ascii=False),
            },
        )
        return entry_of(Path(dest).name, dest, False, size, fsid=int(created.get("fs_id") or 0))

    def _safe_name(self, raw: str) -> str:
        name = Path(raw or "未命名").name.strip() or "未命名"
        try:
            name = name.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        return name.strip() or "未命名"

    def _assert_quota(self, account: dict[str, Any], need: int) -> None:
        """空间不够时直接拦住，避免走到 create 才报含糊的 -10。"""
        info = self.quota(account)
        if not info["total"]:
            return
        if info["remain"] >= need:
            return
        raise ValueError(
            f"网盘空间不足（已用 {info['used_text']}，容量 {info['total_text']}），请先删文件或开通会员后再上传"
        )

    def _upload_dest(self, account: dict[str, Any], folder: str, filename: str) -> str:
        name = self._safe_name(filename)
        base = normalize_path(folder) if folder else self.default_root(account)
        dest = join_path(base, name)
        root = self.default_root(account)
        if root != "/" and dest != root and not dest.startswith(root.rstrip("/") + "/"):
            dest = join_path(root, name)
        return dest

    def _ensure_dir(self, account: dict[str, Any], folder: str) -> None:
        folder = normalize_path(folder)
        if folder == "/":
            return
        try:
            self.list_dir(account, folder)
            return
        except ValueError:
            pass
        parent, name = folder.rsplit("/", 1)
        self._ensure_dir(account, parent or "/")
        try:
            self.mkdir(account, parent or "/", name)
        except ValueError:
            pass

    def download(self, account: dict[str, Any], path: str, fsid: int) -> tuple[str, bytes]:
        name, response, client = self.open_download(account, path, fsid)
        try:
            return name, response.read()
        finally:
            response.close()
            client.close()

    def open_download(self, account: dict[str, Any], path: str, fsid: int):
        token = self._token(account)
        if not fsid:
            raise ValueError("缺少文件编号，请重新打开这个文件夹")
        data = self._xpan(
            "GET",
            "/multimedia",
            {"method": "filemetas", "fsids": json.dumps([int(fsid)]), "dlink": 1},
            account,
        )
        rows = data.get("list") if isinstance(data.get("list"), list) else []
        if not rows or not isinstance(rows[0], dict):
            raise ValueError("找不到这个文件")
        dlink = str(rows[0].get("dlink") or "")
        name = str(rows[0].get("filename") or path.rsplit("/", 1)[-1] or "下载")
        if not dlink:
            raise ValueError("百度没给下载地址")
        # 不能用 params= 再拼 access_token，会把 sign 重新编码，百度会报 31023。
        url = f"{dlink}{'&' if '?' in dlink else '?'}access_token={token}"
        client = httpx.Client(timeout=None, follow_redirects=True)
        req = client.build_request("GET", url, headers={"User-Agent": _UA})
        response = client.send(req, stream=True)
        if response.status_code >= 400:
            try:
                err = response.json()
                code = int(err.get("error_code") or err.get("errno") or 0)
                msg = _msg(code, "下载失败")
            except Exception:
                msg = "下载失败"
            response.close()
            client.close()
            raise ValueError(msg)
        return name, response, client

    def apply_tokens(self, account: dict[str, Any], tokens: dict[str, Any]) -> dict[str, Any]:
        account.update(tokens)
        try:
            account["user_label"] = self.user_label(account)
        except ValueError:
            pass
        return account

    def _tokens_from(self, data: dict[str, Any]) -> dict[str, Any]:
        token = str(data.get("access_token") or "")
        if not token:
            raise ValueError("百度没返回授权")
        return {
            "access_token": token,
            "refresh_token": str(data.get("refresh_token") or ""),
            "expires_at": int(time.time()) + int(data.get("expires_in") or 0),
        }

    def _token(self, account: dict[str, Any]) -> str:
        token = str(account.get("access_token") or "")
        if not token:
            raise ValueError("还没授权")
        return token

    def _manager(self, account: dict[str, Any], opera: str, filelist: list) -> None:
        data = self._xpan(
            "POST",
            "/file",
            {"method": "filemanager", "opera": opera},
            account,
            data={"async": 0, "filelist": json.dumps(filelist, ensure_ascii=False)},
        )
        info = data.get("info")
        if isinstance(info, list):
            for row in info:
                if isinstance(row, dict) and int(row.get("errno") or 0) != 0:
                    raise ValueError(_msg(int(row.get("errno") or 0), "操作失败"))

    def _xpan(self, method: str, path: str, params: dict[str, Any], account: dict[str, Any], data: dict | None = None) -> dict[str, Any]:
        token = self._token(account)
        query = {"access_token": token, **params}
        body = self._json(method, f"{_XPAN}{path}", params=query, data=data)
        errno = int(body.get("errno") or 0)
        if errno in {111, -6, 31045} and account.get("refresh_token"):
            tokens = self.refresh(account)
            account.update(tokens)
            query["access_token"] = tokens["access_token"]
            body = self._json(method, f"{_XPAN}{path}", params=query, data=data)
            errno = int(body.get("errno") or 0)
        if errno != 0:
            raise ValueError(_msg(errno))
        return body

    def _json(self, method: str, url: str, params: dict | None = None, data: dict | None = None) -> dict[str, Any]:
        with httpx.Client(timeout=40) as client:
            res = client.request(method, url, params=params, data=data, headers={"User-Agent": _UA})
        return self._as_json(res)

    def _as_json(self, res: httpx.Response) -> dict[str, Any]:
        try:
            data = res.json()
        except Exception as exc:
            raise ValueError("百度返回的不是正常数据") from exc
        if not isinstance(data, dict):
            raise ValueError("百度返回的不是正常数据")
        return data

    def _oauth_error(self, data: dict[str, Any]) -> str:
        text = str(data.get("error_description") or data.get("error") or "授权失败")
        mapping = {
            "invalid_client": "AppKey 或 SecretKey 不对",
            "invalid_grant": "授权码无效或已用过",
            "expired_token": "授权超时，请重新点授权",
        }
        return mapping.get(str(data.get("error") or ""), text)
