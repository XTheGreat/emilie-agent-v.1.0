"""The little video-call window: a separate OS window (Tk) that shows the camera, like a picture-in-picture.

Run as a child process:  python -m emilie.callwindow <width> <height>
It reads raw RGB frames (width*height*3 bytes each) from stdin. When stdin closes (the call ended) or the window is
closed by the user, it exits; the parent notices the closed pipe and ends the call. Mirrored, always on top.
"""
import os
import sys
import threading
import tkinter as tk

from PIL import Image, ImageDraw, ImageOps, ImageTk

TITLE = "Emilie - video call"


def main() -> int:
    w, h = int(sys.argv[1]), int(sys.argv[2])
    root = tk.Tk()
    root.title(TITLE)
    root.configure(bg="#141414")
    root.attributes("-topmost", True)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    ww, wh = 400, round(400 * h / w)
    root.geometry(f"{ww}x{wh}+{max(0, sw - ww - 28)}+{max(0, sh - wh - 90)}")      # bottom-right, like a call window
    root.minsize(160, round(160 * h / w))
    label = tk.Label(root, bg="#141414", bd=0)
    label.pack(fill="both", expand=True)
    state = {"frame": None, "seq": 0, "shown": 0, "eof": False, "photo": None}
    lock = threading.Lock()

    def reader() -> None:
        n = w * h * 3
        src = sys.stdin.buffer
        while True:
            buf = src.read(n)
            if len(buf) < n:
                break
            with lock:
                state["frame"] = buf
                state["seq"] += 1
        state["eof"] = True

    threading.Thread(target=reader, daemon=True).start()

    def close(*_):
        root.destroy()

    root.bind("<Escape>", close)
    root.bind("q", close)
    root.protocol("WM_DELETE_WINDOW", close)

    ppid = os.getppid()

    def tick() -> None:
        if state["eof"] or os.getppid() != ppid:      # call ended, or the app died: do not linger
            root.destroy()
            return
        with lock:
            buf, seq = state["frame"], state["seq"]
        if buf is not None and (seq != state["shown"] or state.get("size") != (label.winfo_width(), label.winfo_height())):
            state["shown"] = seq
            cw, ch = max(32, label.winfo_width()), max(32, label.winfo_height())
            state["size"] = (cw, ch)
            img = ImageOps.mirror(Image.frombuffer("RGB", (w, h), buf, "raw", "RGB", 0, 1))      # mirrored, like a call
            scale = min(cw / w, ch / h)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR)
            d = ImageDraw.Draw(img)
            d.ellipse((8, 8, 18, 18), fill=(255, 85, 119))                                       # "recording" dot
            d.text((24, 6), "CAM", fill=(255, 255, 255))
            photo = ImageTk.PhotoImage(img)
            label.configure(image=photo)
            state["photo"] = photo                                                               # keep a reference
        root.after(33, tick)

    tick()
    root.mainloop()
    # Leave NOW. A normal exit waits for the reader thread, which is blocked reading stdin: on Windows that took ~6 s
    # and then crashed (0xC0000005), so the app only noticed the closed window seconds later.
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
