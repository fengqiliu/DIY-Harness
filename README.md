# DIY Personal Harness

这是一套给个人开发者使用的本地工作流程。你可以在 Codex、Claude 或终端中开始一项任务，让同一个人或助手先后承担规划、实现、评审和验证。每次交接都带上结论和证据；切换会话后，用任务 ID 即可找回目标、当前阶段和历史记录。

## 从一项任务开始

在本目录使用 Python 3.10 或更高版本。唯一第三方依赖是 PyYAML。以下命令可直接在 PowerShell 中运行。

```powershell
python -m pip install -r requirements.txt
python scripts/verify.py
python scripts/bootstrap.py feature --run-id report-search --task "为本地报告列表增加按检查号精确查找。验收覆盖有匹配和无匹配两种结果。"
python scripts/checkpoint.py report-search --brief
```

`--brief` 给出本阶段的负责人、技能、交付要求、最近一次交接及启动时的协作约定。把任务目标中的项目路径指向你的实际仓库，让当前助手根据简报完成工作。也可以直接在终端里按简报自行执行。

下面是一条**示例交接**。实际登记时，替换为你确认过的结论及证据。证据可以是可观察的输入输出、目标仓库中的文档位置，或可重跑的命令与实测结果。

```powershell
python scripts/checkpoint.py report-search --stage requirements --outcome pass --summary "已确定精确匹配与空结果的验收条件" --evidence "合成验收样例：已有 A100 和 A1001 时，查 A100 只返回 A100；查 Z999 返回空列表。"
python scripts/checkpoint.py report-search
python scripts/checkpoint.py report-search --history
```

此时当前阶段为 `design`。按每个阶段的简报继续执行，最后一次 `verify` 阶段通过后运行 `python scripts/verify.py report-search` 校验闭环。该命令重放阶段与证据记录；业务证据的真实性和充分性由执行者在目标项目验收。

## 体系如何分工

| 要回答的问题 | 对应文件 | 什么时候使用 |
| --- | --- | --- |
| 你希望助手怎样工作？ | [AGENTS.md](AGENTS.md)、[context/](context/) | 根规则、个人偏好、工程习惯和架构判断进入新任务快照。[CLAUDE.md](CLAUDE.md) 引用同一份规则。 |
| 谁来做，怎样做？ | [agents/](agents/)、[skills/](skills/) | 角色定义责任与交接对象，技能定义该类工作的判断方法。阶段简报只展开当前角色与技能。 |
| 用哪套流程和模型？ | [config/](config/)、[workflows/](workflows/) | 注册流程名，配置角色的模型偏好、权限约定、阶段顺序及失败后的去向。 |
| 上次做到哪里？ | [scripts/](scripts/)、[runs/](runs/) | CLI 初始化任务、登记检查点、核对完成状态。每个任务在本地拥有独立 SQLite 文件。 |
| 哪些做法可跨任务复用？ | [memory/decisions.md](memory/decisions.md)、[memory/lessons.md](memory/lessons.md) | 人工整理已确认的取舍和经验证的经验，注明来源及适用边界。按任务需要查阅。 |
| 修改流程后还能用吗？ | [evals/](evals/) | 使用临时任务副本验证正常推进、返工、恢复和非法操作。 |

### 两条内置工作流

| 流程 | 正常顺序 | 返工规则 |
| --- | --- | --- |
| `feature` | `requirements → design → implement → review → verify` | 评审或验收失败回到 `implement`，修正后再次评审和验收。 |
| `bugfix` | `reproduce → fix → review → verify` | 评审或验收失败回到 `fix`，保留失败记录，使用原条件复查。 |

每个检查点可登记 `pass`（推进）、`fail`（按 `on_fail` 返工）或 `blocked`（保留当前阶段）。没有填写 `on_fail` 的阶段失败后停在本阶段。阻塞解除后，再对同一阶段登记实际结果。每条记录都要求结论和至少一项证据，重复 `--evidence` 可附多项。

### 恢复任务和跨会话交接

```powershell
python scripts/checkpoint.py report-search --history
python scripts/checkpoint.py report-search --brief
```

新会话可以直接使用这条指令：“继续任务 `report-search`。先读取当前简报和历史证据，在目标仓库完成当前阶段，再登记实际结果。”

同一任务有多人或多会话处理时，在写入命令中增加 `--revision N`，其中 `N` 是接手时状态行里的修订号。其他会话已登记新结果时，脚本会提示先读取最新交接。任务内记录保存在 `runs/<任务ID>/run.sqlite3`；例行备份可在写入结束后复制整个任务目录。

## 按自己的工作方式调整

1. **个人习惯**　改 [profile.md](context/profile.md) 中的语言和交付偏好。把可复用的验收习惯写进 [engineering.md](context/engineering.md)，项目特有的接口、环境和操作命令留给目标仓库。
2. **角色与模型**　在 [models.yaml](config/models.yaml) 增加模型别名并分配到角色。默认 `session-default` 沿用当前会话；CLI 将偏好显示在简报中，实际模型由宿主选择。角色切换可由同一助手完成。
3. **权限边界**　在 [permissions.yaml](config/permissions.yaml) 维护本地操作、需另行授权操作与资料处理约定。这里的文字供执行者判断，工具调用的强制限制由宿主及操作系统执行。
4. **阶段与技能**　复制 [feature.yaml](workflows/feature.yaml)，修改阶段 ID、角色、技能、交付要求和可选 `on_fail`，在 [工作流注册表](config/workflows.yaml) 增加名称与路径。新技能放在 `skills/<名称>/SKILL.md`，元数据中的 `name` 与目录名一致。
5. **配置生效时间**　新任务读取修改后的配置和规则。已有任务继续使用启动时的快照。长期记忆由你选择写入时机，运行记录默认留在本机。

## 自检

```powershell
python scripts/verify.py
python -B -m unittest discover -s evals -v
```

第一条检查工作流引用、阶段 ID、失败回退目标、模型映射与技能元数据。第二条通过三个 CLI 的正常入口运行合成用例。对单个任务，`python scripts/verify.py RUN_ID` 在记录完整且所有阶段最终通过时返回退出码 0；任务未完成或记录检查失败时返回非零。登记 `blocked` 或 `fail` 成功时，检查点命令返回 0，表示该结果已保存。
