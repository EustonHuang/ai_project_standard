<!-- 自动生成，请勿手改；改动会被脚本覆盖 -->

# Architecture — TOC

> 由 `append_history.py gen-toc` 自动生成；每版本正文见 `architecture/{ver}.md`。

- [v001 · 初版设计：history.json 纯数组 + per-event schema_version](architecture/001.md) — 状态：历史
- [v002 · 文件夹形态：history/ questions/ issues/ architecture/ + 根索引与 meta + 锁与 issues 兜底](architecture/002.md) — 状态：历史
- [v003 · 改进：删 *_meta.json（plan 级字段并入 architecture_index）、删 plan_001/002、TOC 扩展四类 + gen-toc + show 尾部窗口](architecture/003.md) — 状态：历史
- [v004 · 项目规范框架化：skill→元规范、独立 git/GitHub 仓库、install/update/check skills、improvements 栏目、README 改名、双版本轴分离](architecture/004.md) — 状态：历史
- [v005 · 采用方上下文自动加载：install 写入 .codebuddy/rules 总是类规则（alwaysApply）+ 重名强制替代](architecture/005.md) — 状态：历史
- [v006 · 采纳方实测暴露的三处框架缺口修复：结构守卫(IMP-001) / 发布链(IMP-002) / 版本可追溯(IMP-003)](architecture/006.md) — 状态：历史
- [v007 · 网关强化：.turngateignore 通用忽略 + PreToolUse 写时硬拦截（目标 v0.7）](architecture/007.md) — 状态：历史
- [v008 · 自定义 feature 机制：项目根 custom/ 容器下 custom/<feature>/ + 同名 index/TOC（均在容器内）；registry 声明驱动，扁平有序 md 记录，无 frontmatter/版本字段/审批门禁（v0.8）](architecture/008.md) — 状态：历史
- [v009 · 会话全录器（session recorder）：进程外 daemon + feeder hooks + 被动 watcher，trace 落盘 plan root 之外，opt-in 安装（目标 v0.9）](architecture/009.md) — 状态：已落地
