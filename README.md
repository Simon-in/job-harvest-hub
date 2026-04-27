# job-harvest-hub

一个可发布的多平台招聘数据采集与分析项目，基于 FastAPI + Playwright + SQLite。

支持平台：
- boss（Boss 直聘）
- liepin（猎聘）
- zhilian（智联招聘）

## 功能特性

- 多平台统一任务入口（按 platform 切换）
- 登录流程（弹窗手动登录）+ Cookie 持久化复用
- 实时进度推送（SSE）
- 本地 SQLite 持久化（岗位数据、配置、Cookie）
- 前端管理页（配置、任务状态、岗位列表、统计）
- 一键清空岗位数据（API）

## 技术栈

- Python 3.10+
- FastAPI
- Playwright
- SQLite
- Pydantic

## 项目结构

```text
job-harvest-hub/
  app/
    api/
      routes.py
    repository/
      jobs_repo.py
      config_repo.py
      cookie_repo.py
    services/
      boss_service.py
      liepin_service.py
      zhilian_service.py
      login_flow_service.py
      progress_hub.py
    web/
      index.html
      app.js
      style.css
    config.py
    database.py
    main.py
  db/
  requirements.txt
  README.md
```

## 安装与启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 启动服务

```bash
uvicorn app.main:app --reload --port 8888
```

### 3. 访问地址

- 前端页面: http://127.0.0.1:8888/
- Swagger 文档: http://127.0.0.1:8888/docs
- ReDoc 文档: http://127.0.0.1:8888/redoc

## 关键 API

### 基础

- GET /api/health
- GET /api/tasks/platforms

### 配置与任务

- GET /api/tasks/options?platform=boss|liepin|zhilian
- GET /api/tasks/config?platform=...
- POST /api/tasks/config
- POST /api/tasks/start
- POST /api/tasks/stop?platform=...
- GET /api/tasks/status?platform=...
- GET /api/tasks/progress/stream?platform=...

### 登录与 Cookie

- POST /api/tasks/login/start?platform=...&timeout_sec=180
- GET /api/tasks/login/status?platform=...
- POST /api/tasks/login/clear?platform=...

### 数据查询与清理

- GET /api/tasks/list?platform=...&page=1&size=20
- GET /api/tasks/stats?platform=...
- POST /api/tasks/data/clear?scope=all
- POST /api/tasks/data/clear?scope=platform&platform=boss

## 发布到 GitHub 建议

1. 仓库命名建议：job-harvest-hub
2. 保留以下文件：
   - README.md
   - LICENSE
   - .gitignore
3. 不提交本地运行产物：
   - db/*.db
   - __pycache__/
   - .venv/

## 免责声明

本项目仅用于学习与技术研究，请遵守目标平台服务条款与当地法律法规。

## License

MIT License
