# job-harvest-hub

job-harvest-hub 是一个面向个人求职与岗位研究场景的招聘数据采集与分析工具。

它希望解决一个实际问题：
当你每天要看大量岗位描述（JD）时，如何更高效地收集、筛选、沉淀，并进一步用于简历优化与投递准备。

说明：当前版本不直接采集 JD 正文，主要采集岗位基础字段与职位链接。

项目基于 FastAPI + Playwright + SQLite，提供了可视化管理页、任务控制、进度跟踪和本地数据沉淀能力。

## 支持平台

- boss（Boss 直聘）
- liepin（猎聘）
- zhilian（智联招聘）

## 你可以用它做什么

- 用统一入口采集不同平台的岗位数据
- 通过关键词、城市、薪资等条件进行任务配置
- 复用登录 Cookie，减少重复登录操作
- 在页面中查看任务状态、实时进度和采集结果
- 将岗位数据沉淀到本地 SQLite，用于后续分析与联动

## 当前数据边界

- 当前稳定采集：岗位名称、公司、薪资、城市、经验、学历、职位链接等基础字段。
- 当前不稳定/不支持：直接批量抓取完整 JD 正文。
- 与简历项目联动时，需要人工点击职位链接查看 JD，再将 JD 内容输入 resume-as-code。

## 平台状态与已知问题

- zhilian（智联招聘）：可用，关键词链路已适配当前站点行为。
- liepin（猎聘）：可用，已采用页面内关键词提交并校验结果页。
- boss（Boss 直聘）：当前不可用（暂不建议使用）。

### Boss 直聘当前问题

- 即使手动登录成功，也可能立即跳转到未知页面，登录态无法稳定保持。
- 采集流程难以持续停留在可用列表页，可能出现空结果或任务中断。
- 当前版本尚未实现稳定的 Boss 登录态固定方案。

### 当前建议

- 正式任务优先使用 zhilian / liepin。
- Boss 功能仅建议用于调试验证，不建议用于生产使用。

## 快速开始

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

## 使用流程（推荐）

1. 选择平台并填写关键词、城市、薪资、最大页数等参数。
2. 点击“登录并保存 Cookie”（如平台需要）。
3. 启动任务并观察“任务状态 + 实时进度日志”。
4. 在分析页查看岗位列表与统计结果。
5. 根据需要导出或继续清洗本地数据。

## 关键 API 一览

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

## 与 resume-as-code 联动

你可以将本项目与 resume-as-code 联动，形成“岗位筛选 -> 手动提取 JD -> 定向简历生成”的流程。

- 项目地址（GitHub）：https://github.com/zhiweio/resume-as-code

联动价值：
- job-harvest-hub 负责采集岗位基础信息与职位链接（岗位名称、薪资、公司、城市、职位链接等）。
- resume-as-code 负责根据 JD 自动生成更匹配的简历版本。
- 组合使用后，可用于批量岗位研究、定向简历生成和投递前准备。

推荐流程：
1. 在本项目按关键词采集并筛选目标岗位。
2. 从本地数据中获取岗位链接并人工打开职位详情页。
3. 手动提取 JD 关键信息（岗位职责、任职要求、技术栈、业务背景等）。
4. 将整理后的 JD 内容输入 resume-as-code，生成定制化简历。
5. 对生成结果进行人工校对后再投递。

实践建议：
- 按岗位方向分组（后端/算法/测试等）维护多套简历版本。
- 优先使用最近采集的 JD，减少过期信息干扰。
- 保留同岗位的多个简历版本，提高匹配率。

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

## 技术栈

- Python 3.10+
- FastAPI
- Playwright
- SQLite
- Pydantic

## 致谢

感谢以下开源项目提供的思路与启发：

- get_jobs（架构组织与部分工程实现思路参考）：https://github.com/loks666/get_jobs

## 免责声明

本项目仅用于学习与技术研究，请遵守目标平台服务条款与当地法律法规。

## License

MIT License
