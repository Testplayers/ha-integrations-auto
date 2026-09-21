# ha-integrations-auto

> Home Assistant 公用事业集成（水 / 电 / 气）的**自动更新托管仓库**。
> GitHub Actions 每周检查上游有没有新版本，有就自动 vendor 进来；HA 定时拉取应用。

## 这个仓库干什么

```
┌──────────────── 每周一 10:00（GitHub Actions）────────────────┐
│  检查上游：                                                  │
│   • stevenjoezhang/hass-state-grid   （电，跟 main 分支）     │
│   • yahooor/zr-gas-ha                （气，跟最新 release）  │
│  有变化 → 下载 → 覆盖 integrations/ → 更新 versions.json      │
│  → 自动 commit（GitHub 上有完整变更历史，可审可回滚）          │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────── HA 容器内（每周一 12:00 / 手动）──────────────┐
│  sync_integrations.sh                                        │
│   下载本仓库 tar.gz → 对比 versions.json 与本地状态           │
│   → 有更新则覆盖 /config/custom_components/<名>/             │
│   → HA 通知 + 重启 Core                                      │
└──────────────────────────────────────────────────────────────┘
```

- **检测在 GitHub**：有 Actions 日志、有 commit 历史，改了什么一目了然
- **应用在 HA**：只做「拉取 + 覆盖 + 重启」，逻辑简单不易坏
- **不覆盖自研集成**：`longyan_water` 标记为 `self`，只登记版本，永不被替换

## 目录结构

```
ha-integrations-auto/
├── .github/workflows/update.yml   # 每周自动检查上游（也可手动 Run workflow）
├── build.py                       # 检测 + vendor 脚本（Actions 和本地都用它）
├── versions.json                  # 当前各集成版本/来源/时间（HA 侧据此判断是否更新）
├── integrations/
│   ├── longyan_water/             # 自研（来源：本地）
│   ├── state_grid/                # 电，来自上游 main
│   └── zr_gas/                    # 气，来自上游 release
└── ha/
    └── sync_integrations.sh       # 部署到 HA /config/ 的同步脚本
```

## 在 HA 侧启用

复制 `ha/sync_integrations.sh` 到 HA 的 `/config/`（即 `/homeassistant/`），然后：

**1. 手动跑一次（验证能通）**

```bash
docker exec homeassistant bash /config/sync_integrations.sh --check-only
```

**2. 加 shell_command**（`/config/shell_commands.yaml`，并在 `configuration.yaml` 里 `shell_command: !include shell_commands.yaml`）

```yaml
sync_integrations: bash /config/sync_integrations.sh
sync_integrations_check: bash /config/sync_integrations.sh --check-only
```

**3. 加自动化**（每周一 04:10 自动同步，见 `ha/automation_example.yaml`）

```yaml
- id: auto_sync_integrations
  alias: 每周同步集成更新
  triggers:
    - trigger: time
      at: "04:10:00"
  conditions:
    - condition: time
      weekday: [mon]
  actions:
    - action: shell_command.sync_integrations
```

## 手动操作

```bash
# 在 HA 容器里
docker exec -it homeassistant bash
bash /config/sync_integrations.sh --check-only   # 只看看有没有更新
bash /config/sync_integrations.sh                # 更新 + 重启
bash /config/sync_integrations.sh --no-restart   # 更新但不重启
tail -50 /config/sync_integrations.log           # 看历史日志
```

或在 HA 界面：开发者工具 → 操作 → `shell_command.sync_integrations` → 调用。

## 本地跑 build.py

```bash
python build.py            # 有变化才写文件
python build.py --force    # 强制全部重新拉取
```

输出末尾的 `CHANGED: ...` 是 workflow 判断是否需要 commit 的依据。

## 上游来源

| 集成 | 上游 | 许可 |
|---|---|---|
| `state_grid` | [stevenjoezhang/hass-state-grid](https://github.com/stevenjoezhang/hass-state-grid) | 见上游 |
| `zr_gas` | [yahooor/zr-gas-ha](https://github.com/yahooor/zr-gas-ha) | MIT |
| `longyan_water` | 自研（[Testplayers/longyan-water-ha](https://github.com/Testplayers/longyan-water-ha)） | MIT |

版权归各自作者所有，本仓库仅做自动化搬运，方便内网 HA 拉取。
