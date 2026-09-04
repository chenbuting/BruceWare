# BruceWare

个人工作台。左边点模块，右边同一块工作区打开，不另开窗口。

## 技术

| 层级 | 技术 |
|------|------|
| 网页 | React + Vite + TypeScript + Tailwind |
| 后端 | Python 3.11+ + FastAPI |
| 数据库 | 默认 SQLite，也可在设置里改成远程 MySQL / PostgreSQL |

## 启动

先复制配置（已有 `.env` 可跳过）：

```bash
copy .env.example .env
```

启动后端：

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

## 现在有什么

- **网站入口**：收藏常用网站
- **简历**：保存、AI 分析、打字模拟面试
- **衣橱**：衣服图、试穿和搭配
- **文件**：管理本机或服务器上的文件夹
- **知识库**：多个库整理资料，可分文件夹和标签，支持预览、提问和可选 Wiki

设置里配数据源、AI、文件根目录。选了根目录后，衣橱图和本地库会放在根目录下的 `BruceWare` 里；设置文件仍留在程序的 `data/app-settings.json`。

## 目录

```
BruceWare/
  apps/api/      后端
  apps/web/      网页
  modules/       各功能模块的说明
  docs/design/   设计文档（知识库等）
  data/          本机设置（不要提交）
```

知识库已接整理、提问、库规则和可选 Wiki。设计：[docs/design/知识库总体设计.md](docs/design/知识库总体设计.md)、[docs/design/知识库详细设计.md](docs/design/知识库详细设计.md)。
