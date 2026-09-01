# BruceWare

个人工作台底座。网页是总入口，功能以后按模块往里加。

## 技术

| 层级 | 技术 |
|------|------|
| 网页 | React + Vite + TypeScript + Tailwind |
| 后端 | Python 3.11+ + FastAPI |
| 数据库 | 默认 SQLite，可在 `.env` 改成远程 MySQL / PostgreSQL |

## 启动

先复制配置（已有 `.env` 可跳过）：

```bash
copy .env.example .env
```

启动后端（安装依赖并打开接口服务）：

```bash
cd apps/api
pip install -r requirements.txt
python run.py
```

后端：http://127.0.0.1:8000  
接口文档：http://127.0.0.1:8000/docs

另开一个终端，启动网页：

```bash
cd apps/web
npm install
npm run dev
```

网页：http://127.0.0.1:5173

## 换数据源

打开网页「设置」，选本地 SQLite 或远程 MySQL / PostgreSQL，先测试再保存。  
保存后写到 `data/app-settings.json`，不必改 `.env`。

## 目录

```
BruceWare/
  apps/api/      后端
  apps/web/      网页壳
  modules/       以后放各功能模块（现在是空的）
```
