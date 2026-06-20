"""builder.merge.blacklist — 阶段四·纯客户端 Mod 黑名单。

纯客户端模组在服务端加载会导致渲染类缺失崩溃。本模块维护已知纯客户端模组的
modid / 文件名关键字集合，供 client_cleaner 查询匹配。

重要：以下类型的 mod 在 NeoForge 服务端有实际功能，不应被禁用：
- JEI / REI — 服务端配方同步，且其他 mod 可能声明对其的硬依赖
- iris / oculus / sodium / embeddium — NeoForge 版本包含服务端逻辑，
  且其他 mod（如 colorwheel）可能声明对 iris 的硬依赖
- modernfix — 包含服务端优化（chunk loading, recipe caching 等）
- journeymap — 服务端路点同步 & 世界映射
- lithium — NeoForge 版本包含服务端 tick 优化
"""
from __future__ import annotations

# ── 已知纯客户端模组的关键字集合（全小写匹配） ──────────────────────
# 仅包含在服务端 **毫无作用** 或 **必定崩溃** 的 mod。
# 对于有争议的 mod（如 JEI、sodium），宁可保留也不要误杀——
# 服务端多加载一个 mod 只消耗少量内存，误杀则导致依赖链断裂崩溃。
_CLIENT_MOD_BLACKLIST: set[str] = {
    # ── 渲染 & 光影（纯客户端渲染管线，服务端无对应逻辑） ──
    "optifine",
    "phosphor",
    "starlight",
    "colorwheel",          # 着色器管理，纯客户端渲染
    "colorwheel_patcher",  # colorwheel 补丁
    "euphoriapatcher",     # 光影补丁（Euphoria Patches）
    "immediatelyfast",     # 客户端渲染批处理优化
    "modelfix",            # 模型修复，纯客户端渲染
    "flickerfix",          # 屏幕闪烁修复，纯客户端
    "ctm",                 # Connected Textures Mod，纯客户端纹理连接
    # ── 光影包（.zip 文件，纯客户端着色器） ──
    "bslshaders",
    "complimentaryshaders",
    "seuspbr",
    # ── 客户端 UI & HUD 辅助（纯视觉，无服务端同步） ──
    "inventoryprofilesnext",
    "inventoryhud",
    "appleskin",           # 食物饱和度 HUD
    "notenoughitems",
    "betteradvancements",  # 成就 UI 美化
    "darkmodeeverywhere",  # 暗色模式
    "overloadedarmorbar",  # 护甲条 UI 增强
    "colorfulhearts",      # 彩色血条
    "moreoverlays",        # 覆盖层 UI（矿洞查找等）
    "prism",               # 资源包 UI 美化
    "searchables",         # 搜索 UI 库（fancymenu 依赖）
    "smithingtemplateviewer",  # 锻造模板查看器
    # ── 主菜单 & 加载屏（纯客户端 UI） ──
    "fancymenu",           # 自定义主菜单
    "drippyloadingscreen", # 加载屏美化
    "custommainmenu",      # 自定义主菜单（旧版）
    "packmenu",            # 整合包主菜单
    # ── 按键 & 鼠标（纯客户端输入） ──
    "controlling",         # 按键绑定搜索 UI
    "mousetweaks",         # 鼠标拖拽物品
    "keybindbundles",      # 按键绑定包
    "keybindspurger",      # 按键清除
    "rebind_narrator",     # 重绑定叙述者键
    "justzoom",            # 缩放功能
    # ── 动画 & 视觉效果（纯客户端感官增强） ──
    "notenoughanimations", # 动画增强
    "cleanswing",          # 挥手动画
    "soundphysics",
    "presencefootsteps",
    "dynamicfps",
    "entityculling",
    "entitytexturefeatures",
    "continuity",
    "fpsreducer",
    "betterthirdperson",
    "betterf3",
    # ── 音频（纯客户端） ──
    "extremesoundmuffler", # 声音调节
    "melody",              # 音乐播放器 UI
    # ── 启动优化（纯客户端侧） ──
    "smoothboot",
    "smoothbootreloaded",
    "fastload",
    "memorysettings",      # 内存设置 UI
    # ── 小地图（纯客户端渲染，无服务端同步） ──
    "xaerominimap",
    "xaeroworldmap",
    "xaerominimapfairplay",
    "minimap",
    "mapwriter",
    "antiqueatlas",
    # ── Toast & 提示控制（纯客户端） ──
    "toastcontrol",        # Toast 提示控制
    "yeetusexperimentus",  # 实验性功能过滤
    # ── 崩溃助手（纯客户端崩溃报告 UI） ──
    "crashassistant",
    # ── 其他客户端工具库 ──
    "konkrete",            # fancymenu/drippy 等的客户端 UI 库
    "lmft",                # Loading Message Font Tweaks
    # ── 记录/回放 ──
    "replaymod",
}

# ── 以下 mod 在 NeoForge 服务端有实际功能，不应被禁用 ──────────────
# 保留此注释列表供参考，避免未来误加回黑名单：
#   jei / justenoughitems  — 服务端配方同步；其他 mod 硬依赖
#   rei / roughlyenoughitems — 同上
#   iris / oculus — NeoForge 版含服务端逻辑；colorwheel 等硬依赖
#   sodium / embeddium / rubidium — NeoForge 版含服务端逻辑；iris 依赖
#   sodiumextras / sodium-extra — sodium 扩展
#   lithium — 服务端 tick 优化
#   modernfix — 服务端优化（chunk loading, recipe caching）
#   journeymap — 服务端路点同步 & 世界映射


def is_client_mod(filename: str) -> bool:
    """判断 .jar 文件是否命中纯客户端模组黑名单。

    匹配策略：将文件名（去 .jar 后缀）转为小写后，检查是否包含或被包含于
    黑名单中任一关键字。

    Args:
        filename: .jar 文件名（如 "Sodium-0.5.3.jar"）。

    Returns:
        True 表示应从服务端禁用。
    """
    stem = filename.lower().removesuffix(".jar")
    for keyword in _CLIENT_MOD_BLACKLIST:
        if keyword in stem or stem in keyword:
            return True
    return False
