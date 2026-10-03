using System.Runtime.InteropServices;

namespace UsageWidget;

/// WinUI 3 창을 배경만 진짜로 투명하게 만드는 Win32 쪽 처리.
/// WinUI는 최상위 창의 바탕면을 WM_ERASEBKGND에서 흰색(밝은 테마)/검정(어두운 테마)으로 불투명하게 칠한다.
/// blur-behind(빈 영역)로 DWM이 알파를 반영하게 하고, 그 바탕면을 검정(알파 0)으로 칠하면 창 뒤가 비친다.
/// 검정이 아니면 흰색이 그대로 남아서 밝은 색 배경은 투명해지지 않는다. (WinUIEx의 TransparentTintBackdrop도 같은 방식)
static class WindowTransparency
{
    public const uint WM_ERASEBKGND = 0x0014;

    [StructLayout(LayoutKind.Sequential)]
    struct DWM_BLURBEHIND { public uint dwFlags; public int fEnable; public IntPtr hRgnBlur; public int fTransitionOnMaximized; }
    [StructLayout(LayoutKind.Sequential)]
    struct RECT { public int Left, Top, Right, Bottom; }

    [DllImport("dwmapi.dll")] static extern int DwmEnableBlurBehindWindow(IntPtr hwnd, ref DWM_BLURBEHIND bb);
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    [DllImport("gdi32.dll")] static extern IntPtr CreateRectRgn(int l, int t, int r, int b);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr h);
    [DllImport("gdi32.dll")] static extern IntPtr GetStockObject(int i);
    [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr hwnd, out RECT rc);
    [DllImport("user32.dll")] static extern int FillRect(IntPtr hdc, ref RECT rc, IntPtr brush);
    [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr hwnd);
    [DllImport("user32.dll")] static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);

    const int BLACK_BRUSH = 4, DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_NONE = 1;

    /// 투명 모드를 켠다. 되돌리는 경로는 없다: Mica로 돌아갈 때 검은 면이 남는 위험을 피하려고 실행이 끝날 때까지 유지한다.
    public static void Enable(IntPtr hwnd)
    {
        // Mica에서 넘어온 경우 DWM의 Mica 종류가 남아 있으면 투명 대신 Mica가 비친다
        var none = DWMSBT_NONE;
        DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ref none, sizeof(int));

        var rgn = CreateRectRgn(-2, -2, -1, -1); // 창 밖 1px: 블러 없이 알파 합성만 켠다
        var bb = new DWM_BLURBEHIND { dwFlags = 0x1 | 0x2, fEnable = 1, hRgnBlur = rgn }; // DWM_BB_ENABLE | DWM_BB_BLURREGION
        DwmEnableBlurBehindWindow(hwnd, ref bb);
        DeleteObject(rgn);

        // 이미 흰색/검정으로 칠해진 바탕면은 다음 지우기까지 남으므로 지금 검정으로 칠한다
        var dc = GetDC(hwnd);
        if (dc == IntPtr.Zero) return;
        try { EraseBlack(hwnd, dc); }
        finally { ReleaseDC(hwnd, dc); }
    }

    /// WM_ERASEBKGND 처리: 클라이언트 영역을 검정(알파 0)으로. 스톡 브러시라 만들거나 지울 GDI 개체가 없다.
    public static void EraseBlack(IntPtr hwnd, IntPtr hdc)
    {
        if (GetClientRect(hwnd, out var rc)) FillRect(hdc, ref rc, GetStockObject(BLACK_BRUSH));
    }
}
