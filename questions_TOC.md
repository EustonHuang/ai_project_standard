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
