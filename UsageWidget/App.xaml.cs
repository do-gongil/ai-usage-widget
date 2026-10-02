using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.Runtime.InteropServices;
using System.Windows.Input;
using H.NotifyIcon;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.ApplicationModel;
using S = UsageWidget.UsageService;

namespace UsageWidget;

public partial class App : Application
{
    const string StartupTaskId = "UsageWidgetStartup"; // Package.appxmanifest의 StartupTask TaskId와 같아야 한다
    // 단일 인스턴스: 둘이 동시에 돌면 usage API 호출이 두 배가 돼 429에 걸린다
    const string MutexName = @"Local\UsageTray.SingleInstance";
    static readonly Dictionary<string, string> ViewLabels = new() { ["five_hour"] = "5", ["weekly"] = "W" };

    Mutex? _mutex;
    Config _cfg = null!;
    MainWindow _pip = null!;
    TaskbarIcon _tray = null!;
    Icon? _icon;
    Dictionary<string, AgentResult> _last = new();
    Dictionary<string, AgentResult> _results = new();
    DateTime? _updatedAt;
    AgentResult? _claudePrev;
    long _claudeUntil; // Environment.TickCount64 기준, 이 시각 전엔 Claude 조회 안 함
    int _claudeBackoff;
    long _claudeOkAt; // 마지막 조회 성공 시각 (TickCount64)
    TaskCompletionSource _wake = new(TaskCreationOptions.RunContinuationsAsynchronously);
    bool _stopped;

    public App()
    {
        InitializeComponent();
        // 처리 못한 UI 예외로 트레이 앱이 메시지 없이 사라지지 않게: 삼키고 툴팁에 사유만 남긴다
        UnhandledException += (_, e) =>
        {
            e.Handled = true;
            if (_tray != null) _tray.ToolTipText = S.BuildTooltip([$"오류: {e.Exception.GetType().Name}"]);
        };
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        _mutex = new Mutex(true, MutexName, out var created);
        if (!created) { Exit(); return; }

        _cfg = Config.Load();
        _last = Config.LoadLast();

        _pip = new MainWindow(_cfg);
        _pip.RefreshRequested += () => _wake.TrySetResult();
        _tray = new TaskbarIcon
        {
            ToolTipText = "Usage Tray",
            ContextFlyout = BuildMenu(),
            LeftClickCommand = new Command(() => _pip.SetVisible(!_pip.IsShown)),
            NoLeftClickDelay = true,
        };
        _tray.ForceCreate(enablesEfficiencyMode: false);

        // 첫 조회 전: 저장된 직전 값을 회색으로 먼저 표시
        if (_cfg.Claude) _results["claude"] = new(Error: "조회 중");
        if (_cfg.Codex) _results["codex"] = new(Error: "조회 중");
        Draw();
        if (_cfg.PipVisible) _pip.SetVisible(true);
        _ = LoopAsync();
    }

    // ---------- 트레이 메뉴 ----------

    sealed class Command(Action run) : ICommand
    {
        public event EventHandler? CanExecuteChanged { add { } remove { } }
        public bool CanExecute(object? p) => true;
        public void Execute(object? p) => run();
    }

    MenuFlyout BuildMenu()
    {
        // 체크 상태는 설정값에서 다시 계산한다 (팝업 메뉴 모드에서 IsChecked 자동 토글에 기대지 않음)
        ToggleMenuFlyoutItem claude = null!, codex = null!, pip = null!, autostart = null!;
        MenuFlyoutItem view = null!;
        claude = new() { Text = "Claude", IsChecked = _cfg.Claude, Command = new Command(() => { claude.IsChecked = _cfg.Claude = !_cfg.Claude; Toggled(); }) };
        codex = new() { Text = "Codex", IsChecked = _cfg.Codex, Command = new Command(() => { codex.IsChecked = _cfg.Codex = !_cfg.Codex; Toggled(); }) };
        pip = new() { Text = "PiP 보기", IsChecked = _cfg.PipVisible, Command = new Command(() => _pip.SetVisible(!_pip.IsShown)) };
        view = new() { Text = ViewMenuText(), Command = new Command(() =>
        {
            _cfg.View = _cfg.View == "five_hour" ? "weekly" : "five_hour";
            _cfg.Save();
            view.Text = ViewMenuText();
            Draw();
        }) };
        autostart = new() { Text = "시작 시 실행", Command = new Command(async () => await SetAutostart(!await AutostartEnabled())) };

        var menu = new MenuFlyout();
        menu.Opening += async (_, _) =>
        {
            pip.IsChecked = _pip.IsShown; // 창 닫기 버튼으로 숨긴 경우도 반영
            autostart.IsChecked = await AutostartEnabled();
        };
        foreach (var item in new MenuFlyoutItemBase[]
                 {
                     claude, codex, new MenuFlyoutSeparator(), pip, view,
                     new MenuFlyoutItem { Text = "지금 새로고침", Command = new Command(() => _wake.TrySetResult()) },
                     autostart,
                     new MenuFlyoutItem { Text = "종료", Command = new Command(Quit) },
                 })
            menu.Items.Add(item);
        return menu;
    }

    string ViewMenuText() => _cfg.View == "five_hour" ? "아이콘: 주간 보기" : "아이콘: 5시간 보기";

    void Toggled()
    {
        _cfg.Save();
        _wake.TrySetResult();
    }

    void Quit()
    {
        _stopped = true;
        try
        {
            _pip.SaveRect();
            _tray.Dispose();
            _icon?.Dispose();
        }
        finally { Exit(); } // 정리 중 예외가 나도 종료는 한다. 뮤텍스는 프로세스 종료 시 OS가 해제
    }

    // ---------- 조회 루프 ----------

    async Task<AgentResult> ClaudeAsync()
    {
        var now = Environment.TickCount64;
        if (!S.ShouldFetch(_claudePrev, now, _claudeUntil, _claudeOkAt))
            return _claudePrev!; // 429 대기 중이거나 직전 성공 후 5분 미만: 직전 결과 재사용
        var result = await S.FetchClaudeAsync();
        if (result.Usage != null) _claudeOkAt = Environment.TickCount64;
        if (result.RetryAfter != null)
        {
            _claudeBackoff = S.RetryDelay(result.RetryAfter, _claudeBackoff);
            _claudeUntil = now + _claudeBackoff * 1000L;
        }
        else _claudeBackoff = 0;
        _claudePrev = result;
        return result;
    }

    async Task RefreshAsync()
    {
        var results = new Dictionary<string, AgentResult>();
        if (_cfg.Claude) results["claude"] = await ClaudeAsync();
        if (_cfg.Codex) results["codex"] = await Task.Run(S.ReadCodex);

        var lines = new List<string>();
        foreach (var (agent, name) in new[] { ("claude", "Claude"), ("codex", "Codex") })
        {
            if (!results.TryGetValue(agent, out var r)) continue;
            lines.Add(S.FormatLine(name, r, _last.GetValueOrDefault(agent)));
            if (r.Usage != null) _last[agent] = r;
        }
        if (results.Values.Any(r => r.Usage != null)) Config.SaveLast(_last);
        if (_stopped) return;

        _results = results;
        _updatedAt = DateTime.Now;
        if (lines.Count > 0) lines.Add($"갱신 {_updatedAt:HH:mm:ss}");
        _tray.ToolTipText = S.BuildTooltip(lines);
        Draw();
    }

    async Task LoopAsync()
    {
        // UI 스레드에서 돈다: 조회는 await(비동기 I/O)라 창이 멈추지 않는다
        while (!_stopped)
        {
            try { await RefreshAsync(); }
            catch (Exception e) // 루프가 죽으면 아이콘이 멈춘 채 남으므로 사유를 툴팁으로
            {
                try
                {
                    SetIcon(RenderIcon(null, true, null));
                    _tray.ToolTipText = S.BuildTooltip([$"오류: {e.GetType().Name}"]);
                }
                catch (Exception) { } // 표시에 실패해도 루프는 계속 돈다
            }
            await Task.WhenAny(_wake.Task, Task.Delay(TimeSpan.FromSeconds(_cfg.Interval)));
            _wake = new(TaskCreationOptions.RunContinuationsAsynchronously);
        }
    }

    void Draw()
    {
        var (pct, stale) = S.IconState(_results, _last, _cfg.View);
        SetIcon(RenderIcon(pct, stale, ViewLabels[_cfg.View]));
        _pip.Update(_results, _last, _updatedAt);
    }

    // ---------- 아이콘 (render_icon 이식) ----------

    [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr handle);

    void SetIcon(Icon icon)
    {
        _tray.UpdateIcon(icon);
        _icon?.Dispose(); // 셸은 아이콘을 복사해 가므로 이전 것은 해제
        _icon = icon;
    }

    static System.Drawing.Color Hex(string hex) => ColorTranslator.FromHtml(hex);

    /// stale=true: 조회 실패로 직전 값을 보여주는 중 → 회색 배경.
    /// label: 좌측 상단 어두운 뱃지 글자 ('5' 5시간 / 'W' 주간). 뱃지만큼 숫자는 오른쪽 아래로.
    static Icon RenderIcon(double? pct, bool stale, string? label)
    {
        const int size = 64;
        using var bmp = new Bitmap(size, size);
        using (var g = Graphics.FromImage(bmp))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            using var bg = new SolidBrush(Hex(stale ? S.ColorUnknown : S.ColorFor(pct)));
            using (var path = RoundedRect(new Rectangle(0, 0, size - 1, size - 1), label != null ? 8 : 10))
                g.FillPath(bg, path);
            var text = S.IconText(pct);
            if (label != null)
            {
                using var badge = new SolidBrush(Hex("#1d2230"));
                g.FillRectangle(badge, 0, 0, 25, 27);
                DrawCentered(g, label, 26, new RectangleF(0, 0, 25, 27));
                DrawCentered(g, text, 40, new RectangleF(8, 20, 56, 46));
            }
            else DrawCentered(g, text, text.Length == 1 ? 46 : 40, new RectangleF(0, 0, size, size));
        }
        var hicon = bmp.GetHicon();
        try
        {
            using var tmp = Icon.FromHandle(hicon);
            return (Icon)tmp.Clone();
        }
        finally { DestroyIcon(hicon); }
    }

    static void DrawCentered(Graphics g, string text, float px, RectangleF box)
    {
        using var font = new Font("Segoe UI", px, System.Drawing.FontStyle.Bold, GraphicsUnit.Pixel);
        using var fmt = new StringFormat(StringFormat.GenericTypographic)
            { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
        g.DrawString(text, font, Brushes.White, box, fmt);
    }

    static GraphicsPath RoundedRect(Rectangle r, int radius)
    {
        var p = new GraphicsPath();
        var d = radius * 2;
        p.AddArc(r.X, r.Y, d, d, 180, 90);
        p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
        p.CloseFigure();
        return p;
    }

    // ---------- 시작 시 실행 ----------

    // MSIX 앱은 HKCU\Run 쓰기가 패키지 안으로 가상화돼 효과가 없다 → StartupTask(매니페스트 확장) 사용.
    // 패키지 ID 없이(dotnet run 등) 실행하면 예외 → 꺼진 것으로 취급.

    static async Task<bool> AutostartEnabled()
    {
        try
        {
            var task = await StartupTask.GetAsync(StartupTaskId);
            return task.State is StartupTaskState.Enabled or StartupTaskState.EnabledByPolicy;
        }
        catch (Exception) { return false; }
    }

    static async Task SetAutostart(bool enabled)
    {
        try
        {
            var task = await StartupTask.GetAsync(StartupTaskId);
            // 사용자가 작업 관리자 > 시작 앱에서 끈 경우(DisabledByUser) 앱이 다시 켤 수 없다 (Windows 정책)
            if (enabled) await task.RequestEnableAsync();
            else task.Disable();
        }
        catch (Exception) { }
    }
}
