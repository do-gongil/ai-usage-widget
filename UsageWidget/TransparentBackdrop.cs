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

    protected override void OnTargetConnected(ICompositionSupportsSystemBackdrop target, XamlRoot xamlRoot)
    {
        base.OnTargetConnected(target, xamlRoot);
        EnsureDispatcherQueue(); // 시스템 Compositor는 Windows.System.DispatcherQueue가 있는 스레드에서만 만들 수 있다
        _compositor ??= new Windows.UI.Composition.Compositor();
        target.SystemBackdrop = _compositor.CreateColorBrush(Windows.UI.Color.FromArgb(0, 0, 0, 0));
    }

    protected override void OnTargetDisconnected(ICompositionSupportsSystemBackdrop target)
    {
        base.OnTargetDisconnected(target);
        target.SystemBackdrop = null;
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
