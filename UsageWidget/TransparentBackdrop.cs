using System.Runtime.InteropServices;
using Microsoft.UI.Composition;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;

namespace UsageWidget;

/// 창 배경을 완전히 투명하게 하는 backdrop. 그 위에 반투명 배경 브러시를 깔면
/// 배경만 비치고 글씨·막대는 불투명하게 남는다 (layered 창 알파는 글씨까지 흐려진다).
sealed class TransparentBackdrop : SystemBackdrop
{
    static Windows.UI.Composition.Compositor? _compositor;
    readonly IntPtr _hwnd;
    public TransparentBackdrop(IntPtr hwnd) => _hwnd = hwnd;

    protected override void OnTargetConnected(ICompositionSupportsSystemBackdrop target, XamlRoot xamlRoot)
    {
        base.OnTargetConnected(target, xamlRoot);
        EnsureDispatcherQueue(); // 시스템 Compositor는 Windows.System.DispatcherQueue가 있는 스레드에서만 만들 수 있다
        _compositor ??= new Windows.UI.Composition.Compositor();
        target.SystemBackdrop = _compositor.CreateColorBrush(Windows.UI.Color.FromArgb(0, 0, 0, 0));
        // 이게 없으면 창 표면이 불투명이라 알파 배경이 검정 위에 섞여 색만 어두워진다.
        // 빈 영역으로 blur-behind를 켜면 DWM이 창을 per-pixel 알파로 합성한다.
        SetBlurBehind(true);
    }

    protected override void OnTargetDisconnected(ICompositionSupportsSystemBackdrop target)
    {
        base.OnTargetDisconnected(target);
        target.SystemBackdrop = null;
        SetBlurBehind(false);
    }

    [StructLayout(LayoutKind.Sequential)]
    struct DWM_BLURBEHIND { public uint dwFlags; public int fEnable; public IntPtr hRgnBlur; public int fTransitionOnMaximized; }
    [DllImport("dwmapi.dll")] static extern int DwmEnableBlurBehindWindow(IntPtr hwnd, ref DWM_BLURBEHIND bb);
    [DllImport("gdi32.dll")] static extern IntPtr CreateRectRgn(int l, int t, int r, int b);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr h);

    void SetBlurBehind(bool on)
    {
        var rgn = CreateRectRgn(-2, -2, -1, -1); // 화면 밖 1px: 실제 블러 없이 투명 합성만 켠다
        var bb = new DWM_BLURBEHIND { dwFlags = 0x1 | 0x2, fEnable = on ? 1 : 0, hRgnBlur = rgn }; // DWM_BB_ENABLE | DWM_BB_BLURREGION
        DwmEnableBlurBehindWindow(_hwnd, ref bb);
        DeleteObject(rgn);
    }

    [StructLayout(LayoutKind.Sequential)]
    struct DispatcherQueueOptions { public int dwSize, threadType, apartmentType; }
    [DllImport("CoreMessaging.dll")]
    static extern int CreateDispatcherQueueController(DispatcherQueueOptions options, out IntPtr controller);
    static IntPtr _controller; // 해제하면 큐가 사라지므로 앱이 끝날 때까지 붙잡아 둔다

    static void EnsureDispatcherQueue()
    {
        if (Windows.System.DispatcherQueue.GetForCurrentThread() != null || _controller != IntPtr.Zero) return;
        // DQTYPE_THREAD_CURRENT = 2, DQTAT_COM_NONE = 0
        CreateDispatcherQueueController(new() { dwSize = Marshal.SizeOf<DispatcherQueueOptions>(), threadType = 2 }, out _controller);
    }
}
