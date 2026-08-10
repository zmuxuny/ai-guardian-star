"""华为无障碍色彩对比度自检。

规则（design-guides/ux-guidelines-general，「色彩」章节）：
    图标、标题文字与背景对比度 >= 3:1
    正文文字与背景对比度 >= 4.5:1

这里只登记「人工确认过会同框出现」的前景/背景配对，改色后直接跑：
    python tools/check_contrast.py
"""


def _lum(hex_color: str) -> float:
    v = hex_color.lstrip("#")
    out = 0.0
    for channel, weight in zip((v[0:2], v[2:4], v[4:6]), (0.2126, 0.7152, 0.0722)):
        c = int(channel, 16) / 255
        out += weight * (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def ratio(fg: str, bg: str) -> float:
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def blend(fg: str, bg: str, alpha: float) -> str:
    """把半透明前景压平到不透明色，用于 rgba(...) 文字。"""
    f, b = fg.lstrip("#"), bg.lstrip("#")
    out = ""
    for i in (0, 2, 4):
        fc, bc = int(f[i:i + 2], 16), int(b[i:i + 2], 16)
        out += f"{round(bc + (fc - bc) * alpha):02x}"
    return "#" + out


# (说明, 前景, 背景, 最低比例)
PAIRS = [
    # 登录页：Logo 区文字所处的渐变段最亮到 #2f6fe0，是最不利情形
    ("登录页 标题「智护星」", "#ffffff", "#2f6fe0", 3.0),
    ("登录页 标语", "#ffffff", "#2f6fe0", 4.5),
    ("登录页 登录按钮文字", "#ffffff", "#2563eb", 4.5),
    ("登录页 登录按钮 loading", "#ffffff", "#64748b", 4.5),
    ("登录页 获取验证码按钮", "#ffffff", "#2563eb", 4.5),
    # 卡片内文字（浅色主题卡片为纯白）
    ("链接文字 linkTextColor", "#1D4ED8", "#FFFFFF", 4.5),
    ("成功文字 successTextColor", "#047857", "#FFFFFF", 4.5),
    ("警告文字 warningTextColor", "#B45309", "#FFFFFF", 4.5),
    ("错误文字 dangerTextColor", "#DC2626", "#FFFFFF", 4.5),
    ("次级文字 secondaryTextColor", "#475569", "#FFFFFF", 4.5),
    ("三级文字 tertiaryTextColor", "#64748B", "#FFFFFF", 4.5),
    # 深色主题卡片 #1E293B
    ("暗色 链接文字", "#60A5FA", "#1E293B", 4.5),
    ("暗色 成功文字", "#34D399", "#1E293B", 4.5),
    ("暗色 警告文字", "#FBBF24", "#1E293B", 4.5),
    ("暗色 错误文字", "#F87171", "#1E293B", 4.5),
    ("暗色 三级文字", "#94A3B8", "#1E293B", 4.5),
    # 徽标 / 按钮
    ("MyAddress 默认徽标", "#ffffff", "#1d4ed8", 4.5),
    ("Index 同意按钮", "#ffffff", "#2563eb", 4.5),
    ("person 退出登录按钮", "#ffffff", "#dc2626", 4.5),
    ("person 注销账号文字", "#b91c1c", "#fee2e2", 4.5),
    ("mainpage 设备离线徽标", "#ffffff", "#dc2626", 4.5),
    ("Profile 头像编辑图标", "#ffffff", "#2563eb", 3.0),
    ("person 注销弹窗 获取验证码", "#ffffff", "#2563eb", 4.5),
    ("person 注销弹窗 确认按钮", "#ffffff", "#dc2626", 4.5),
    ("mainpage 通话按钮（通话中）", "#ffffff", "#dc2626", 4.5),
    ("mainpage 通话按钮（待机）", "#ffffff", "#2563eb", 4.5),
]


def main() -> int:
    failed = 0
    for name, fg, bg, need in PAIRS:
        got = ratio(fg, bg)
        if got < need:
            failed += 1
            print(f"FAIL {got:5.2f} < {need}  {name}  {fg} on {bg}")
    print(f"{len(PAIRS) - failed}/{len(PAIRS)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
