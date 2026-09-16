"""百度网盘官方接口。个人应用一般只能进 /apps/应用名/。"""

from __future__ import annotations

import hashlib
import json
import time
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
    -7: "文件或目录不存在",
    -9: "文件不存在",
    2: "参数不对",
    111: "授权过期，请重新授权",
    31023: "参数不对",
    31034: "请求太勤，请稍后再试",
    31045: "授权失败，请重新授权",
    31061: "文件已存在",
    31066: "文件不存在",
    31299: "只能访问应用目录，请把应用名称填成开放平台上的应用名",
    31326: "命中反作弊，请稍后再试",
    42213: "没有权限访问这个目录",
}


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
                {"method": "list", "dir": folder, "start": start, "limit": 200, "order": "name"},
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
            {"method": "search", "key": query.strip(), "dir": folder, "recursion": 1, "num": 100},
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
                )
            )
        return {"root": self.default_root(account), "path": folder, "crumbs": crumbs(folder), "items": items}

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
        src = normalize_path(path)
        folder = normalize_path(dest or self.default_root(account))
        name = src.rsplit("/", 1)[-1]
        self._manager(account, "move", [{"path": src, "dest": folder, "newname": name}])
        return entry_of(name, join_path(folder, name), False)

    def delete(self, account: dict[str, Any], path: str) -> None:
        self._manager(account, "delete", [normalize_path(path)])

    def upload(self, account: dict[str, Any], path: str, filename: str, data: bytes) -> dict[str, Any]:
        dest = join_path(path or self.default_root(account), filename)
        blocks = [data[index : index + _CHUNK] for index in range(0, max(len(data), 1), _CHUNK)] or [b""]
        md5s = [hashlib.md5(chunk).hexdigest() for chunk in blocks]
        pre = self._xpan(
            "POST",
            "/file",
            {"method": "precreate"},
            account,
            data={
                "path": dest,
                "size": str(len(data)),
                "isdir": "0",
                "autoinit": "1",
                "rtype": "1",
                "block_list": json.dumps(md5s, ensure_ascii=False),
            },
        )
        if int(pre.get("return_type") or 0) == 2:
            return entry_of(filename, dest, False, len(data), fsid=int(pre.get("fs_id") or 0))
        upload_id = str(pre.get("uploadid") or "")
        if not upload_id:
            raise ValueError("百度没给上传号")
        token = self._token(account)
        for index, chunk in enumerate(blocks):
            with httpx.Client(timeout=120) as client:
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
                    files={"file": ("blob", chunk, "application/octet-stream")},
                )
            body = self._as_json(res)
            if int(body.get("errno") or 0) != 0 and "md5" not in body:
                raise ValueError(_msg(int(body.get("errno") or 0), "分片上传失败"))
        created = self._xpan(
            "POST",
            "/file",
            {"method": "create"},
            account,
            data={
                "path": dest,
                "size": str(len(data)),
                "isdir": "0",
                "rtype": "1",
                "uploadid": upload_id,
                "block_list": json.dumps(md5s, ensure_ascii=False),
            },
        )
        return entry_of(filename, dest, False, len(data), fsid=int(created.get("fs_id") or 0))

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
        client = httpx.Client(timeout=None, follow_redirects=True)
        req = client.build_request(
            "GET",
            dlink,
            params={"access_token": token},
            headers={"User-Agent": _UA},
        )
        response = client.send(req, stream=True)
        if response.status_code >= 400:
            response.close()
            client.close()
            raise ValueError("下载失败")
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
