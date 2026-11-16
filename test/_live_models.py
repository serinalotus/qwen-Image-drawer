"""真机验证：用本机真实配置启动窗口 → 点「刷新可用模型」→ 截图 → 关闭。"""

import os
import sys
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "test"))

import app as app_module  # noqa: E402
import ui_theme  # noqa: E402
from smoke import screenshot, wait_idle  # noqa: E402

app_module.enable_dpi_awareness()
ui_theme.enable_dpi_awareness()
root = tk.Tk()
application = app_module.App(root)

for _ in range(30):
    root.update()
    time.sleep(0.05)

print("启动后模型:", application.form.model_var.get())
print("启动后尺寸:", application.form.size_var.get(), "->", application.form.get_payload()["size"])

application.refresh_models()
deadline = time.time() + 40
while time.time() < deadline:
    root.update()
    time.sleep(0.05)
    if not getattr(application, "_refreshing_models", False):
        break

names = list(application.form.model_combo.cget("values"))
print("刷新后下拉项数:", len(names))
print("新增项:", [n for n in names if "服务端" in n])
print("状态文本:", application.form.settings_hint.cget("text"), "|", application.form.model_desc.cget("text"))

# 滚到输出设置卡片
application.form.scroll.canvas.yview_moveto(1.0)
for _ in range(20):
    root.update()
    time.sleep(0.03)

out = ROOT / "test" / "out" / "live-models.png"
image = screenshot(root, "live-models.png")
print("截图:", image)

root.after(50, application.on_close)
root.mainloop()
print("closed")
