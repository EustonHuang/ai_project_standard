<!-- 自动生成，请勿手改；改动会被脚本覆盖 -->

# Questions — TOC

> 由 `append_history.py gen-toc` 自动生成；每问答正文见 `questions/{num}.md`。

- [Q1](questions/001.md) — `history.json` 里 event #1 的 `user_prompt` 只是个索引：「（见 event #2 的 user_prompt；本 history.json 的初始化是创建该 skill 流程的一部分）」。请问 event #2 在哪？我怎么查看？
- [Q2](questions/002.md) — 为什么到目前为止每个 event 都含有「timestamp 精确时刻未知（仅日期确定）」之类的评论？① 为什么 timestamp 拿不到精确时刻？② `recorded_at` 字段已经有时间戳了（这正是我要看的），它和 `timestamp` 字段的区别在哪？有了 `rec…
- [Q3](questions/003.md) — 去掉 `timestamp` 会改变 schema → `schema_version` 必然要变。若改变后，怎么实现 history.json 的只增不改？因为似乎要再加一个 `{}` 表示 `schema_version=1.1`，JSON 会从 `{}` 变成 `[{},{…
- [Q4](questions/004.md) — - `{}` 包裹结构是本 skill 的设计缺陷；原本的 `schema_version` 是「整个文件的 schema_version」，但用户要的是 **event 的 schema_version**，不是文件的。
- [Q5](questions/005.md) — 目前采用的 append-only `history.json` 方式，会不会对 AI coding 不太友好？因为 AI coding 每次都要先扫描一遍文件，然后 append？这样的话当 append 越来越多的时候，会减慢速度？
- [Q6](questions/006.md) — 所以，AI coding 在执行 append 的时候，是怎样的流程？他们真的是读了 `history.json` 以及 `questions.md` 的所有的内容吗？
- [Q7](questions/007.md) — 将 `history.json` 和 `questions.md` 拆成「文件夹 + 文件」的形式：
- [Q8](questions/008.md) — 用户逐条回应了 Q7 的 8 点并补充并发设计，要求：① 审阅；② 在 questions.md 加入审阅结果 + 新计划；③ 更新 history.json（先不执行/不改 plan）。要点：
- [Q9](questions/009.md) — 用户对 A–I 逐条反驳/澄清，指出 B、I 本就是其原意而非"改进"；A 中"文件按顺序排"是助手提出的、用户已用零填充解决；要求把"确认项"改称"需要确认的点"而非"可改进的地方"；并给一条元反馈：提建议要抓主要因素，区分必须做/次要，不要在无关紧要处反复 battle。另要…
- [Q10](questions/010.md) — 现 plan.md 是第一版，且无法得知该 plan 是否已 execute（当前形态是否即 plan.md 的 execute 形态）。提议：
- [Q11](questions/011.md) — meta.json 是否无关紧要？能否计划删除并保证文档同步更新？
- [Q12](questions/012.md) — plan_001.md 与 plan_002.md 是否应删除？
- [Q13](questions/013.md) — questions_TOC.md 是否多余？索引+内容两部分是否真优于单个 questions.json？如何避免索引膨胀回到旧坑？
- [Q14](questions/014.md) — 保留并扩展 TOC 到 architecture/history/issues，但如何写 TOC 需给方案？
- [Q15](questions/015.md) — SKILL.md 哪里写了任何改动都要进 history？为什么你新建 architecture/003.md 和更新索引时忘了记 history？请记到 questions。
- [Q16](questions/016.md) — 希望给个方案以后不许漏记 history：回答最后强制检查本回是否改了 plan 文件、history 是否更新，未更新则强制补；并在 SKILL.md 高亮作双重保险。请加到 questions。
- [Q17](questions/017.md) — 对 Q16 方案的质疑：①第1层举例未加'等'、事件映射未标'举例'，留了钻漏洞空间；②第2层全目录 mtime 扫描既不可扩展又并发误报，应只监测本 agent 本轮改了什么；claude code 有 hook，你有没有这功能？有就用上，没有说怎么实现。请重新梳理三点。
- [Q18](questions/018.md) — history 中 model 永远 Hy3（疑似 #024 实为 Hy4 preview）、schema_version 删 timestamp 后仍 1.0 为何不改？给出根因与方案，记录到 questions；并核查 skill 是否提及『不得就地改、用纠正 note』。
- [Q19](questions/019.md) — 为什么 §8 delta 往后加 10-12/13-14 而不是融进原有 1-9 步？要分多遍执行吗？
- [Q20](questions/020.md) — 为什么还看到 10-12？执行记录保留为 §10 即可，但 §10/§11 问题专章为何不并入前面？
- [Q21](questions/021.md) — 这东西越来越像项目规范而非 skill：每项目都须遵从 history/folder/questions/issues 记录方式，且规范自身也须符合自己并迭代（architecture 001/002/003 即规范版本）；项目层 hook 却引用 skill 层文件很别扭、应放…
- [Q22](questions/022.md) — 确认三决策：框架仓库 git@github.com:EustonHuang/ai_project_standard.git + 本地 ~/personal/ai_project_standard 迁入；首批 skills=install/update/check 放项目下且详写；…
- [Q23](questions/023.md) — 答复 Q22 三确认点：① 框架版本号接受 v<major>.<minor>；② improvements priority=1 Very Low..5 Very High、status=1 Drafting/2 Recorded In Architect/3 Implement…
- [Q24](questions/024.md) — 假设我有一个新的项目，想要运用这个项目规范框架，我应该怎么做？有什么命令或者指示使得我能够在新的项目中"安装"这个项目规范？
- [Q25](questions/025.md) — 下一个问题，你能保证安装项目规范之后，我接下来在这个项目中正常prompting的时候，codebuddy IDE能够把项目规范相关的context给load进去吗？我觉得目前项目规范的安装程度并不能保证这一点吧？
- [Q26](questions/026.md) — 你的意思是，需要加.codebuddy/rules，但是你能保证codebuddy IDE加载的时候先读rules吗？因为之前的实践告诉我codebuddy IDE并没有像claude code那样会先去读CLAUDE.md（对应CODEBUDDY.md和.codebuddy/r…
- [Q27](questions/027.md) — architecture/008.md §1.2 中 record_file（记录正文文件名，默认 record.md）这一项的意义是什么？要求不改设计，并举 3 个例子说明。
- [Q28](questions/028.md) — architecture/008.md 里 custom_categories.json 的 status_flow 和 requires_approval 这两个字段的意义是什么？
- [Q29](questions/029.md) — 回到 Q28：status_flow 解决什么问题？custom/topic_plan/ 下具体 plan（如 spark_lifetime）的状态长什么样、挂哪？requires_approval 什么意思（给具体例子）？这一套是否过度设计？
- [Q30](questions/030.md) — 但凡加一个字段就要考虑怎么维护它；我没说过要加 requires_approval 这些字段。status_flow 的 draft→review→approved→implemented 维护要花多少力气、一处不对就要查原因，收益大吗？你既然认同，为什么还这么设计并替自己辩解？
- [Q31](questions/031.md) — architecture/008.md §1 里 implements_to: topics_meta/<subject>/** 是什么意思？举例详细说明。
- [Q32](questions/032.md) — 你为什么要设计 implements_to？我哪里提示要设计这个？我只是告诉你 custom-feature 的路径和内容格式，没说 implements_to；custom-feature 只是有序记录，未必 implement。当初设计 implements_to 的初衷是什…
- [Q33](questions/033.md) — architecture/008.md 的「3. D3 — 记录规范」是关于什么的记录规范？
- [Q34](questions/034.md) — D3 记录规范的 frontmatter(revision/supersedes/change_summary/aux_files)与 append-only supersedes 修订机制是不是过度设计？我有没有让你设计这个？哪条具体指示要求的？questions/ 下的文件(…
- [Q35](questions/035.md) — 当我让你把问题记在 questions 中时，什么触发了你去做？靠什么保证写 questions/NNN.md、更新 questions_index.json 和 questions_TOC.md 不漏？又靠什么保证 history 不漏？
- [Q36](questions/036.md) — 改了 architecture/008.md，README.md 为啥不改？How to use 提到 questions/improvements 为啥不加 customs？这个需不需要加？
- [Q37](questions/037.md) — 分析你为何傲慢却犯蠢错（008 声称 v0.8 补 README 但计划没写），并解释为什么没听懂我所表达的东西。
- [Q38](questions/038.md) — history/NNN.json 每个字段怎么填（schema_version=2.0、event_type=plan_modified 从哪来/取什么值）？记录靠 skill/hook/还是别的触发？
- [Q39](questions/039.md) — 想在 CodeBuddy session 全录一切（用户 prompt、agent 回答、thinking、skill、写文件、web search、hook、输出）：怎么实现？
- [Q40](questions/040.md) — 不要在当前框架谈「能不能」。我要的是做成全录 session（prompt/回答/thinking/skill/文件/web/hook/输出）的方法。
- [Q41](questions/041.md) — 要录一切 input/output 肯定含 hooks；用 agent 去 trace 会死循环。要跳脱 agent——建独立进程监听 agent 捕获。hooks 怎么被捕获？
- [Q42](questions/042.md) — 把 Q38–Q41 整段讨论收口：到底怎么把 CodeBuddy session 一切（prompt/回答/thinking/skill/文件/web/hook/输出）录下来？作为结论记进 questions。
- [Q43](questions/043.md) — 你的设计为何还在用 hook？以及为何看 .turn 状态有帮助？
- [Q44](questions/044.md) — agent 动作→IDE 触发 hook，这 hook 是 agent 动作第一步吗？hook 本身不会被记录对吧？
- [Q45](questions/045.md) — daemon 是 per-project 还是单进程监控所有项目？生命周期如何（启动/退出/被杀/重拉）？
- [Q46](questions/046.md) — 怎么保证每个项目、每个 session 都被录到（多项目多 session 并发）？
- [Q47](questions/047.md) — architecture 009 实施的六项实测与验收实际结果？
- [Q48](questions/048.md) — 采用本规范的项目都要更新到 v0.9 才能开 tracing 吗？旧版本无所谓吗？
- [Q49](questions/049.md) — per-project 装脚本 vs 单 daemon trace 所有 session，两者矛盾吗？
