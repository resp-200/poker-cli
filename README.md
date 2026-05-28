# 本地多终端德州扑克说明文档

## 1. 项目简介

这是一个命令行格式的本地联机德州扑克小游戏，使用 Python 标准库实现，无需安装第三方依赖。

它支持：

- 一个服务端进程创建牌局。
- 多个终端作为真人玩家加入。
- 多个独立 AI agent 作为客户端加入。
- 服务端内置 AI 玩家，适合快速凑桌。
- 本地 TCP 通信，默认只监听 `127.0.0.1`。


核心文件：

```text
texas_holdem.py  # 游戏主程序
README.md        # 使用说明文档
```

## 2. 环境要求

- macOS / Linux / Windows 均可运行。
- Python 3.10 或更高版本。
- 不需要安装 pip 依赖。

检查 Python 版本：

```bash
python3 --version
```

## 3. 快速开始


### 3.1 一名真人 + 两名独立 AI agent

终端 1：启动服务端，等待 3 名玩家加入。

```bash
python3 texas_holdem.py server --players 3 --bots 0
```

终端 2：真人玩家加入。

```bash
python3 texas_holdem.py client --name zz
```

终端 3：AI agent A 加入。

```bash
python3 texas_holdem.py agent --name AgentA
```

终端 4：AI agent B 加入。

```bash
python3 texas_holdem.py agent --name AgentB
```

当加入人数达到 `--players` 指定数量后，牌局自动开始。

### 3.2 一名真人 + 两名服务端内置 AI

如果不想单独开 AI 终端，可以让服务端直接创建 AI 玩家。

终端 1：

```bash
python3 texas_holdem.py server --players 3 --bots 2
```

终端 2：

```bash
python3 texas_holdem.py client --name zz
```

这里的含义是：总玩家数为 3，其中 2 名是服务端内置 AI，因此只需要 1 名真人客户端加入。

### 3.3 两名真人联机

终端 1：

```bash
python3 texas_holdem.py server --players 2 --bots 0
```

终端 2：

```bash
python3 texas_holdem.py client --name Alice
```

终端 3：

```bash
python3 texas_holdem.py client --name Bob
```

## 4. 命令说明

程序有三个子命令：

```bash
python3 texas_holdem.py server [参数]
python3 texas_holdem.py client [参数]
python3 texas_holdem.py agent [参数]
```

### 4.1 server：启动服务端

示例：

```bash
python3 texas_holdem.py server --host 127.0.0.1 --port 8765 --players 4 --bots 2
```

参数说明：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 服务端监听地址。默认仅本机访问。 |
| `--port` | `8765` | 服务端监听端口。 |
| `--players` | `4` | 总玩家数，包含真人、独立 AI agent 和服务端内置 AI。 |
| `--bots` | `2` | 服务端内置 AI 数量。必须小于总玩家数。 |

注意：

- `--players` 必须在 2 到 9 之间。
- `--bots` 必须小于 `--players`。
- 如果端口被占用，可以换一个端口，例如 `--port 8877`。

### 4.2 client：启动真人客户端

示例：

```bash
python3 texas_holdem.py client --host 127.0.0.1 --port 8765 --name zz
```

参数说明：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 要连接的服务端地址。 |
| `--port` | `8765` | 要连接的服务端端口。 |
| `--name` | `Human` | 玩家昵称。 |

### 4.3 agent：启动独立 AI 客户端

示例：

```bash
python3 texas_holdem.py agent --host 127.0.0.1 --port 8765 --name AgentA
```

参数说明：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 要连接的服务端地址。 |
| `--port` | `8765` | 要连接的服务端端口。 |
| `--name` | `Agent` | AI agent 昵称。 |

独立 AI agent 与真人客户端一样通过 TCP 连接服务端，只是行动由内置策略自动决定。

## 5. 真人操作说明

轮到真人玩家行动时，客户端会展示：

- 当前第几手。
- 公共牌。
- 底池。
- 你的两张手牌。
- 每个玩家的筹码、本轮下注和状态。
- 当前需要跟注的金额。

可输入的操作：

| 输入 | 含义 | 说明 |
| --- | --- | --- |
| `f` | 弃牌 | 放弃本手牌。 |
| `c` | 跟注 | 跟到当前最高下注。 |
| 直接回车 | 跟注 | 等同于 `c`。 |
| `k` | 过牌 | 仅当无需跟注时可用。 |
| `r 40` | 加注 | 加注金额为 40；数字可替换。 |

示例：

```text
请选择行动 [f=弃牌, c=跟注, r 金额=加注, k=过牌]: r 60
```

## 6. 游戏规则实现范围

当前版本已实现：

- 2 到 9 人牌局。
- 初始筹码：每人 1000。
- 小盲：10。
- 大盲：20。
- 发两张手牌。
- 翻牌、转牌、河牌。
- 每轮下注、跟注、过牌、弃牌、加注。
- 摊牌比较牌型。
- 筹码归属和淘汰。
- 游戏持续到只剩一名有筹码的玩家。

牌型比较支持：

1. 皇家同花顺 / 同花顺
2. 四条
3. 葫芦
4. 同花
5. 顺子
6. 三条
7. 两对
8. 一对
9. 高牌

## 7. AI 行为说明

AI 当前是轻量策略，不接入大模型。

它会根据以下因素做简单决策：

- 手牌和公共牌估算强度。
- 当前需要跟注的金额。
- 跟注金额占剩余筹码的压力。
- 强牌时可能加注。
- 弱牌且跟注压力较大时可能弃牌。

独立 AI agent 和服务端内置 AI 使用相近策略。

## 8. 常见玩法组合

### 8.1 真人单挑 AI

```bash
python3 texas_holdem.py server --players 2 --bots 1
python3 texas_holdem.py client --name zz
```

### 8.2 真人对多个独立 AI agent

```bash
python3 texas_holdem.py server --players 4 --bots 0
python3 texas_holdem.py client --name zz
python3 texas_holdem.py agent --name AgentA
python3 texas_holdem.py agent --name AgentB
python3 texas_holdem.py agent --name AgentC
```

### 8.3 全 AI 自动跑牌局

```bash
python3 texas_holdem.py server --players 2 --bots 0
python3 texas_holdem.py agent --name AgentA
python3 texas_holdem.py agent --name AgentB
```

## 9. 故障排查

### 9.1 连接失败

现象：客户端提示无法连接。

处理方式：

1. 确认服务端已启动。
2. 确认客户端和服务端端口一致。
3. 如果修改过 `--host`，确认地址可访问。

### 9.2 端口被占用

现象：服务端启动时报端口占用。

处理方式：换一个端口。

```bash
python3 texas_holdem.py server --port 8877 --players 3 --bots 2
python3 texas_holdem.py client --port 8877 --name zz
```

### 9.3 房间一直等待

现象：服务端显示等待玩家，但牌局没有开始。

原因：已加入玩家数量未达到 `--players`。

处理方式：继续启动客户端或 AI agent，直到人数满足要求。

例如服务端是：

```bash
python3 texas_holdem.py server --players 4 --bots 1
```

表示总共需要 4 名玩家，其中服务端已经内置 1 名 AI，还需要再加入 3 个客户端。

### 9.4 昵称重复

现象：客户端提示昵称已存在。

处理方式：换一个 `--name`。

```bash
python3 texas_holdem.py client --name zz2
```

## 10. 当前限制

为了保持实现简单，当前版本有以下限制：

- 底池按单一主池处理，暂未完整支持复杂边池。
- AI 是规则策略，不是大模型推理。
- 默认只适合本机多终端联机。
- 服务端没有持久化，进程退出后牌局结束。
- 没有账号系统和断线重连机制。

## 11. 验证方式

语法检查：

```bash
python3 -m py_compile texas_holdem.py
```

查看帮助：

```bash
python3 texas_holdem.py --help
python3 texas_holdem.py server --help
python3 texas_holdem.py client --help
python3 texas_holdem.py agent --help
```

本地全 AI 冒烟验证可以开三个终端执行：

```bash
python3 texas_holdem.py server --players 2 --bots 0
python3 texas_holdem.py agent --name AgentA
python3 texas_holdem.py agent --name AgentB
```

看到类似下面的输出表示牌局正常结束：

```text
游戏结束，AgentB 获胜
```
