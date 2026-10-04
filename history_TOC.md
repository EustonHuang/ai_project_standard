<!-- 自动生成，请勿手改；改动会被脚本覆盖 -->

# History — TOC

> 由 `append_history.py gen-toc` 自动生成；每事件正文见 `history/{id}.json`。

- [001 · history_initialized · 2026-10-03T14:56:00](history/001.json) — 初始化 history.json（空 events 数组），为 plan 修订历史建立只增不改的日志。
- [002 · plan_created · 2026-10-03T14:56:00](history/002.json) — 创建 plan-history-recorder skill：定义 history.json 的只增不改事件日志模型、人机分离溯源字段、纠正协议，并提供确定性 append 脚本。
- [003 · plan_modified · 2026-10-03T16:51:16](history/003.json) — 新增 skill 规则：用户提问时，将问题与答案写入 questions.md 并在 history.json 记录 qna_recorded 事件；在 record_types.md 增加 qna_recorded 枚举、workflow.md 增加第7节问答流程、histor
- [004 · qna_recorded · 2026-10-03T16:51:16](history/004.json) — 记录问答 Q1：history.json 中 event #2 的位置与查看方式。
- [005 · qna_recorded · 2026-10-03T16:59:35](history/005.json) — 记录问答 Q2：timestamp 为何不精确、timestamp 与 recorded_at 的区别、能否删 timestamp。
- [006 · qna_recorded · 2026-10-03T17:16:31](history/006.json) — 记录问答 Q3：schema_version 变更与只增不改的冲突及建议（per-event version / 可选字段 / 容器版本 三方案）。
- [007 · qna_recorded · 2026-10-03T17:28:15](history/007.json) — 记录问答 Q4：用户否定 A/B/C，给出正确设计（history.json 纯数组、per-event schema_version、去顶层 meta）；并在 plan.md 写入修订版计划。
- [008 · plan_modified · 2026-10-03T17:41:23](history/008.json) — 执行修订版计划：history.json 改为纯数组 + per-event schema_version；脚本重写为数组操作并新增 migrate；references/SKILL/template 同步；创建 history_meta.json；安装 skill 到 .cod
- [009 · qna_recorded · 2026-10-03T19:32:35](history/009.json) — 记录问答 Q5：append-only history.json 对 AI coding 是否不友好（每次需扫描全文件再 append、append 增长是否变慢）。
- [010 · qna_recorded · 2026-10-03T19:39:19](history/010.json) — 记录问答 Q6：AI coding 执行 append 的真实流程，以及是否真的读全 history.json / questions.md。
- [011 · qna_recorded · 2026-10-03T19:56:29](history/011.json) — 记录问答 Q7：将 history.json → history/{id}_{type}.json、questions.md → questions/{n}.md 的文件夹+文件拆分设计评估。
- [012 · qna_recorded · 2026-10-03T21:41:05](history/012.json) — 记录问答 Q8：审阅用户对 Q7 的答复（零填充命名、history_index.json + issues 兜底、per-plan 索引、简要索引、correction 即文件、乐观锁并发），并给出改进 A–I 与新修改计划。
- [013 · qna_recorded · 2026-10-03T22:26:58](history/013.json) — 记录问答 Q9：用户回应 Q8 的 A–I（重分类确认/改进）、扩展 issues 索引与 meta、锁撤销通知兜底、乐观锁解释、issue 资产具体化、元反馈。
- [014 · qna_recorded · 2026-10-03T23:17:02](history/014.json) — 记录问答 Q10：以 architecture 文件夹替代 plan.md（版本化 md + architecture_index.json 记实现状态 + 每版本含 delta 迁移步骤）。
- [015 · plan_modified · 2026-10-03T23:25:13](history/015.json) — 重命名 plan.md→plan_001.md（初版设计存档）；创建 plan_002.md（整合 Q7–Q10 的执行计划：文件夹化布局、per-category 索引、锁+版本守卫提交、issues 兜底、显式迁移映射 plan_001.md→architecture/001
- [016 · correction · 2026-10-03T23:29:48](history/016.json) — 纠正 plan_002.md：将 *_index.json / *_meta.json 从类目文件夹内移到 <plan>/ 根（用户硬性要求），并同步修正 §1/§5/§6 的所有引用；问答 TOC 移至根 questions_TOC.md。
- [017 · plan_modified · 2026-10-03T23:47:24](history/017.json) — 执行 plan_002.md：迁移到文件夹形态（history/ questions/ issues/ architecture/ + plan 根索引与 meta）；脚本重写为 init/append/show/audit/rebuild-index/migrate/recov
- [018 · qna_recorded · 2026-10-04T00:01:19](history/018.json) — 记录问答 Q11：四个 meta.json 是否无关紧要、能否计划删除并保证文档同步更新。
- [019 · qna_recorded · 2026-10-04T00:01:19](history/019.json) — 记录问答 Q12：plan_001.md 与 plan_002.md 是否应删除。
- [020 · qna_recorded · 2026-10-04T00:01:20](history/020.json) — 记录问答 Q13：questions_TOC.md 是否多余、索引+内容两部分是否真优于单个 questions.json、如何避免索引膨胀回到旧坑。
- [021 · qna_recorded · 2026-10-04T00:07:06](history/021.json) — 记录问答 Q14：保留 TOC 并扩展到 architecture/history/issues，给出具体写法方案。
- [022 · plan_modified · 2026-10-04T00:14:44](history/022.json) — 新建 architecture/003.md（聚合 Q11–Q14 的改进计划：删四个 *_meta.json、删 plan_001/002、TOC 扩展四类 + gen-toc + show 尾部窗口），并将 v3 登记进 architecture_index.json（lat
- [023 · qna_recorded · 2026-10-04T00:17:11](history/023.json) — 记录问答 Q15：SKILL.md 何处规定任何改动要进 history（Purpose 总原则 + When to use 触发项），并复盘漏记 architecture/003.md 创建与索引更新的原因（误把登记索引当记录历史、错误套用 plan_002 规划/执行分期）。
- [024 · qna_recorded · 2026-10-04T09:59:12](history/024.json) — 记录问答 Q16：提出防止漏记 history 的强制方案 —— Turn-end history gate 三层（①SKILL.md 高亮规则+收尾必跑 gate；②新增 gate 子命令机械兜底，受管文件 mtime 新于 last_event_time 即判未记录并 exi
- [025 · qna_recorded · 2026-10-04T10:24:51](history/025.json) — 记录问答 Q17（修订 Q16）：①第 1 层文案补齐'包含但不仅限于…等'与'仅为举例、非穷举'，堵住穷举漏洞；②作废 Q16 的全目录 mtime 扫描，改为 CodeBuddy Hooks 驱动的本轮作用域强检——UserPromptSubmit 开轮记 baseline_
- [026 · plan_modified · 2026-10-04T11:06:37](history/026.json) — 修改 architecture/003.md，把 Q15–Q17 的『防漏记 history』强制门方案整合为第四块工作：①§0/关联/Q14 后新增 Q15–Q17 改进来源，范围扩到 Q11–Q17；②新增 §10 History Update 强制门——第1层 SKILL.
- [027 · qna_recorded · 2026-10-04T11:18:26](history/027.json) — 记录问答 Q18：history 两条数据质量问题（model 自报失真、schema_version 删除 timestamp 后未 bump）的根因分析与解决方案，并核查 skill 已多处明写『不得就地改、用纠正 note』。
- [028 · comment_added · 2026-10-04T11:18:26](history/028.json) — 标注 history 数据质量 lineage：①source.model 全部为 agent 自报『Hy3』，凡用户切换模型的轮次（如疑似 #024 的 Hy4 preview）可能失真，字段不可信；②schema_version 在删 timestamp（形态变更）时未 bu
- [029 · plan_modified · 2026-10-04T11:44:05](history/029.json) — 修改 architecture/003.md 纳入 Q18：①开头范围 Q11–Q17→Q11–Q18，关联行加 Q18 说明；②§0 改进来源 5→6，新增 Q18 来源（model 自报失真 + schema_version 删 timestamp 未 bump）；③新增 §
- [030 · plan_modified · 2026-10-04T12:00:34](history/030.json) — 重写 §8 delta：原分散的 1–14 步（按 Q11–Q14 / Q15–Q17 / Q18 分堆）合并为融合全部改动的 7 步单次连贯执行流（①预备备份 ②索引合并+删冗余 ③重写脚本+新增 turn_gate：含 gen-toc/_regen_toc/show 尾部窗口
- [031 · qna_recorded · 2026-10-04T12:00:34](history/031.json) — 记录问答 Q19：delta 不应按问题分堆追加 10-12/13-14，应融为单次连贯执行流（已重写 §8 为 7 步）。
- [032 · plan_modified · 2026-10-04T12:19:12](history/032.json) — 重构 003.md 章节：删独立的 §10（强制门）与 §11（数据质量修正），其实现细节并入 §5（turn_gate.py 子命令/hook 配置/model 平台信号/EVENT_SCHEMA_VERSION 2.0）与 §6（SKILL 高亮块、workflow hook
- [033 · qna_recorded · 2026-10-04T12:19:12](history/033.json) — 记录问答 Q20：重构计划时不能只压 delta 步骤、仍把每个问题单列成章；应把实现细节并入 §5/§6 等主体章节，章节号随归并重排（原 §12 执行记录→§10）。
- [034 · plan_modified · 2026-10-04T12:28:45](history/034.json) — 执行 architecture/003.md（v3）：① 删除四个 *_meta.json 与 plan_001/002.md，plan 级字段(plan_id/plan_title/created_at)并入 architecture_index.json 顶部，非结构化说明(
- [035 · qna_recorded · 2026-10-04T13:34:28](history/035.json) — 记录 Q21：将本 recorder 重新定位为「全局项目规范（metastandard）」而非 skill；提出全局位置 + 全局 hook 以消除项目层 hook 引用 skill 层文件的别扭；并提出 standard_version（所用规范版本，如003）与项目自身版本
- [036 · qna_recorded · 2026-10-04T14:18:39](history/036.json) — 在 Q21 追加用户补充追问（框架不应再叫 skills、应独立可选采用；git 强制版本控制从 004 起；独立 GitHub 仓库 + 内置 install/update/check skills）及我的补充回应。
- [037 · qna_recorded · 2026-10-04T17:42:41](history/037.json) — 新建 Q22，记录框架仓库/技能/breaking-change 三项决策确认与 improvements 栏目、README 重命名、追问新建 question 三点新提议，并给出 architecture 004 落地细化。
- [038 · qna_recorded · 2026-10-04T17:49:28](history/038.json) — 新建 Q23，记录用户对 Q22 三确认点的答复：版本号 v<major>.<minor>；improvements priority(1-5)/status(Drafting/Recorded In Architect/Implemented)；hook 模型=每采用方项目一份
- [039 · plan_created · 2026-10-04T17:53:56](history/039.json) — 创建 architecture/004.md（项目规范框架化 v0.4），汇总 Q21–Q23：skill→元规范、独立 git/GitHub 仓库、install/update/check skills、breaking-change 类 semver、improvements
