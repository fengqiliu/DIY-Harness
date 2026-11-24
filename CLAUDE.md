# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

协作规范以 [`AGENTS.md`](AGENTS.md) 为准；本文件只补充本仓库（DIY Personal Harness）专属的开发命令与整体结构。

## 常用命令

环境：Python 3.10+，唯一第三方依赖为 PyYAML，推荐在 PowerShell 中运行。

```powershell
# 安装依赖并做基础校验
python -m pip install -r requirements.txt
python scripts/verify.py

# 运行回归测试
python -B -m unittest discover -s evals -v

# 运行单个测试用例
python -B -m unittest evals.test_workflows.WorkflowTests.test_feature_and_bugfix_complete_in_declared_order
```

### 启动与推进任务

```powershell
# 初始化一个 feature 任务
python scripts/bootstrap.py feature --run-id report-search --task "为本地报告列表增加按检查号精确查找。验收覆盖有匹配和无匹配两种结果。"

# 查看当前阶段指引与交接
python scripts/checkpoint.py report-search --brief
python scripts/checkpoint.py report-search --history

# 登记阶段结果（可重复 --evidence）
python scripts/checkpoint.py report-search --stage requirements --outcome pass --summary "已确定精确匹配与空结果的验收条件" --evidence "合成验收样例：查 A100 只返回 A100；查 Z999 返回空列表。"

# 核验某任务是否已闭环
python scripts/verify.py report-search
```

### 阶段结果语义

- `pass`：推进到下一阶段。
- `blocked`：停留在当前阶段，等待阻塞解除后重新对该阶段登记结果。
- `fail`：按阶段 `on_fail` 回到指定阶段（feature/bugfix 的 `review` 与 `verify` 失败后通常回到 `implement`/`fix`）。

## 整体结构

这是一个**本地任务流程与证据交接 Harness**，核心目标是把一次任务拆成固定阶段，并在每个阶段留下可重查的结论与证据。

### 目录职责

| 目录 | 作用 |
| --- | --- |
| `scripts/` | 三个 CLI 入口：`bootstrap.py` 创建任务，`checkpoint.py` 查看/登记，`verify.py` 校验流程或任务闭环。共享逻辑在 `scripts/harness.py`。 |
| `config/` | 运行期配置：`workflows.yaml` 注册流程名到文件；`models.yaml` 定义模型别名与角色映射；`permissions.yaml` 声明权限分组。 |
| `workflows/` | 每个 `.yaml` 描述一组阶段，包含阶段 ID、负责角色、所用技能、交付要求与 `on_fail` 回退目标。 |
| `agents/` | 角色定义（planner、developer、reviewer、verifier），阶段简报会嵌入对应 `.md` 作为角色上下文。 |
| `skills/` | 技能定义，每个子目录一个 `SKILL.md`，元数据 `name` 需与目录名一致。 |
| `context/` | 跨任务通用上下文：`profile.md`（个人偏好）、`engineering.md`（交付习惯）、`architecture.md`（架构判断依据）。 |
| `runs/` | 每个任务一个子目录 `runs/<run_id>/run.sqlite3`，保存启动时的流程快照与所有检查点。 |
| `evals/` | CLI 黑盒回归测试，覆盖正常推进、返工、阻塞、并发冲突与模板编辑隔离。 |

### 关键机制

1. **任务启动时冻结流程快照**。`bootstrap.py` 会把当时的 workflow、角色、技能、权限和通用上下文写入 SQLite。此后修改 `workflows/`、`config/` 或 `context/` 不会影响已有任务，避免跨会话交接时指引漂移。
2. **检查点按记录顺序计算当前阶段**。`checkpoint.py` 读取 SQLite 中的 `events` 表，根据阶段结果和 `on_fail` 路由决定当前应处于哪个阶段；登记失败时会检查 `--revision` 与历史长度是否一致，防止并发覆盖。
3. **所有阶段结果必须带证据**。`--summary` 和至少一项 `--evidence` 是强制的；证据优先引用相对路径、命令与观察值，避免敏感原文。
4. **配置改动需回归验证**。调整流程、角色、技能或上下文后，应运行 `python scripts/verify.py` 与 `python -B -m unittest discover -s evals -v`。

## 进入已有任务时

按 `AGENTS.md` 约定，先读取当前简报和历史证据：

```powershell
python scripts/checkpoint.py RUN_ID --brief
python scripts/checkpoint.py RUN_ID --history
```

然后在任务描述指定的目标仓库中完成当前阶段工作，再回 Harness 登记结果。
