# 目录结构

> builder 模块内部文件组织

---

## 完整目录树

```
builder/
├── __init__.py          # 包入口，导出 build_workspace + 异常类
├── __main__.py          # CLI 入口 (python -m builder)
├── pipeline.py          # 流水线总调度（async）
├── errors.py            # 异常类型定义
│
├── unpack/              # 阶段一：多态解包与资产校验
│   ├── __init__.py
│   ├── safe_extract.py  #   安全解压（Zip Slip 防御）
│   ├── root_locator.py  #   畸形文件树 DFS 下钻
│   ├── discriminator.py #   输入模式判别（InputMode + 服务端/客户端校验）
│   └── validator.py     #   输入合法性校验（语法校验：文件特征检查）
│
├── metadata/            # 阶段二：元数据提取
│   ├── __init__.py
│   ├── curseforge.py    #   CF manifest.json 解析
│   ├── modrinth.py      #   Modrinth index.json 解析
│   └── schema.py        #   统一分发入口
│
├── fetcher/             # 阶段三：多源并发下载
│   ├── __init__.py      #   引擎路由（get_fetcher）
│   ├── sources.py       #   源定义 + URL 构造
│   ├── downloader.py    #   aria2c 主力引擎
│   ├── downloader_httpx.py  # httpx 备用引擎
│   ├── cf_resolver.py   #   CF 文件名解析（API + cloudscraper）
│   ├── pack_search.py   #   整合包名称搜索（CF/Modrinth API）[待实现]
│   └── missing_log.py   #   全网断流日志
│
├── merge/               # 阶段四：资产合并与配置组装
│   ├── __init__.py
│   ├── blacklist.py     #   纯客户端模组黑名单
│   ├── client_cleaner.py#   扫描清洗（.disabled）
│   ├── config_merger.py #   config/kubejs 归并
│   ├── eula_gate.py     #   EULA 交互闸（Protocol+默认实现）
│   └── optional_mods.py #   可选 Mod 识别与 .jar.disabled 处理 [待实现]
│
├── install/             # 阶段五：服务端安装
│   ├── __init__.py
│   ├── installer.py     #   安装器执行 + 产物验证
│   └── java_probe.py    #   Java 运行时探测（声明需求，infra 负责安装）
│
├── launch/              # 启动脚本生成
│   ├── __init__.py
│   └── script_gen.py    #   start.bat / start.sh 生成
│
├── deliver/             # 阶段六：编译与交付
│   ├── __init__.py
│   ├── integrity.py     #   完整性校验
│   └── publisher.py     #   移入 server_pool + 生成报告
│
├── configure/           # 阶段七：服务端配置 [待实现]
│   ├── __init__.py
│   └── server_properties.py  # server.properties 读写
│
└── smoke/               # 阶段八：开服验证 [待实现]
    ├── __init__.py
    ├── launcher.py      #   服务端启动（超时控制）
    └── validator.py     #   启动结果判定 + 崩溃日志提取
```

---

## 命名约定

| 规则 | 示例 |
|---|---|
| 阶段子目录名 = 小写英文 | `unpack/`, `fetcher/`, `merge/` |
| Python 文件名 = 小写下划线 | `safe_extract.py`, `cf_resolver.py` |
| 类名 = PascalCase | `BuildResult`, `EulaGate`, `ConsoleEulaGate` |
| 函数名 = 小写下划线 | `build_workspace()`, `extract_zip()` |
| 常量 = 大写下划线 | `_MAX_RETRY_ROUNDS`, `_GLOBAL_CONCURRENCY` |
| 私有函数 = 下划线前缀 | `_cleanup_sandbox()`, `_generate_input_file()` |

---

## 新增阶段文件的规则

1. 在对应阶段子目录下创建 `.py` 文件
2. 在子目录的 `__init__.py` 中导出公开 API
3. 在 `builder/__init__.py` 中按需重新导出
4. 在 `pipeline.py` 中导入并编排到流水线
5. 更新此文档的目录树
6. 在 `contracts.md` 中记录新增的契约类型（如有）
