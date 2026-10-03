using System.Runtime.InteropServices;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Graphics;
using Windows.UI;

namespace UsageWidget;

/// PiP 창: 항상 위(설정 가능) + 크기 조절. 닫기 = 숨기기.
public sealed partial class MainWindow : Window
{
    readonly Config _cfg;
    readonly OverlappedPresenter _presenter;
    readonly IntPtr _hwnd;
    bool _ready; // 초기값을 컨트롤에 넣는 동안 이벤트 핸들러가 설정을 저장하지 않게
    public event Action? RefreshRequested;

    // 팔레트: null = 기본(Mica 배경, 시스템 테마)
    static readonly (string Name, string? Hex)[] Palette =
    [
        ("기본", null), ("노랑", "#FFF4B8"), ("분홍", "#FFD9EC"), ("하늘", "#D6ECFF"),
        ("연두", "#DDF5D5"), ("보라", "#E8DCFF"), ("어두움", "#202428"),
    ];

    public MainWindow(Config cfg)
    {
        _cfg = cfg;
        InitializeComponent();
        Title = "Usage";
        SystemBackdrop = new MicaBackdrop();
        ExtendsContentIntoTitleBar = true;
        SetTitleBar(DragArea);
        var icon = Path.Combine(AppContext.BaseDirectory, "Assets", "app.ico"); // 작업 표시줄·Alt+Tab 아이콘
        if (File.Exists(icon)) AppWindow.SetIcon(icon); // 파일이 없으면 기본 아이콘 (시작 시 예외로 죽지 않게)

        // CompactOverlay는 크기 조절 폭이 OS 제한에 묶여 있어, 항상 위 + 크기 조절 가능한 일반 창으로 PiP를 만든다
        _presenter = OverlappedPresenter.Create();
        _presenter.IsAlwaysOnTop = cfg.PipTopMost;
        _presenter.IsResizable = true;
        _presenter.IsMaximizable = false;
        _presenter.IsMinimizable = false;
        AppWindow.SetPresenter(_presenter);
        _hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);

        TopMostSwitch.IsOn = cfg.PipTopMost;
        OpacitySlider.Value = cfg.PipOpacity;
        BuildSwatches();
        ApplyColor();
        ApplyOpacity();
        _ready = true;
        ApplyMode();
        RegisterToggleHotkey();
        // 닫기(X) 영역 폭은 창이 그려진 뒤에야 확정되므로 크기가 바뀔 때마다 맞춘다
        Root.SizeChanged += (_, _) => AlignMiniButton();
        // 옮기거나 크기를 바꾸면 곧바로 저장: 재부팅·로그오프로 꺼져도 위치가 유지되게
        AppWindow.Changed += (_, a) => { if (a.DidPositionChange || a.DidSizeChange) ScheduleSave(); };

        AppWindow.Closing += (_, e) => { e.Cancel = true; SetVisible(false); };
    }

    // 모니터 구성이 바뀌어 저장된 위치가 화면 밖이면 기본 위치로
    static bool IsOnScreen(int[] r) =>
        DisplayArea.GetFromRect(new RectInt32(r[0], r[1], r[2], r[3]), DisplayAreaFallback.None) != null;

    public bool IsShown => AppWindow.IsVisible;

    public void SetVisible(bool visible)
    {
        if (visible)
        {
            AppWindow.Show();
            Activate();
        }
        else
        {
            SaveRect();
            AppWindow.Hide();
        }
        _cfg.PipVisible = visible;
        _cfg.Save();
    }

    public void SaveRect()
    {
        if (!AppWindow.IsVisible) return;
        var (p, s) = (AppWindow.Position, AppWindow.Size);
        int[] rect = [p.X, p.Y, s.Width, s.Height];
        if (_cfg.PipMini) _cfg.PipMiniRect = rect;
        else _cfg.PipRect = rect;
        _cfg.Save();
    }

    Microsoft.UI.Dispatching.DispatcherQueueTimer? _saveTimer;

    /// 창 이동·크기 조절·투명도 슬라이더처럼 연달아 바뀌는 값은 마지막 변경 0.5초 뒤 한 번만 저장
    void ScheduleSave()
    {
        if (_saveTimer == null)
        {
            _saveTimer = DispatcherQueue.CreateTimer();
            _saveTimer.Interval = TimeSpan.FromMilliseconds(500);
            _saveTimer.IsRepeating = false;
            _saveTimer.Tick += (_, _) => { if (IsShown) SaveRect(); else _cfg.Save(); };
        }
        _saveTimer.Stop();
        _saveTimer.Start();
    }

    // ---------- 미니 모드 ----------

    void Mini_Click(object sender, RoutedEventArgs e) => ToggleMini();

    /// 일반 창 ↔ 미니 창(상단 행 없이 작업 표시줄 높이). 숨겨져 있었으면 함께 보이게 한다.
    public void ToggleMini()
    {
        SaveRect();
        _cfg.PipMini = !_cfg.PipMini;
        _cfg.Save();
        ApplyMode(keepPosition: true);
        if (!IsShown) SetVisible(true);
    }

    [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr hwnd);
    int Px(double dip) => (int)Math.Round(dip * GetDpiForWindow(_hwnd) / 96.0);

    Microsoft.UI.Dispatching.DispatcherQueueTimer? _resizeTimer;
    RectInt32 _pendingRect;
    void ResizeTick(Microsoft.UI.Dispatching.DispatcherQueueTimer t, object o) => AppWindow.MoveAndResize(_pendingRect);

    /// 미니 모드 버튼을 X 바로 왼쪽에: 오른쪽 여백 = X 버튼 영역 폭 - Root 오른쪽 패딩
    void AlignMiniButton()
    {
        var inset = AppWindow.TitleBar.RightInset * 96.0 / GetDpiForWindow(_hwnd);
        MiniButton.Margin = new Thickness(0, 0, Math.Max(0, inset - Root.Padding.Right), 0);
    }

    /// 지금 위치에서 크기만 바꾸되, 커진 창이 작업 영역(작업 표시줄 제외) 밖으로 나가지 않게 안쪽으로 민다
    static RectInt32 KeepInWorkArea(RectInt32 r)
    {
        var wa = DisplayArea.GetFromRect(r, DisplayAreaFallback.Nearest).WorkArea;
        return new RectInt32(
            Math.Clamp(r.X, wa.X, Math.Max(wa.X, wa.X + wa.Width - r.Width)),
            Math.Clamp(r.Y, wa.Y, Math.Max(wa.Y, wa.Y + wa.Height - r.Height)),
            r.Width, r.Height);
    }

    /// keepPosition: 모드 전환 시 그 모드에 저장된 위치로 튀지 않고 지금 자리에 둔다 (크기만 모드별로 기억)
    void ApplyMode(bool keepPosition = false)
    {
        var mini = _cfg.PipMini;
        Header.Visibility = mini ? Visibility.Collapsed : Visibility.Visible;
        RestoreButton.Visibility = mini ? Visibility.Visible : Visibility.Collapsed;
        Root.Padding = mini ? new Thickness(10, 3, 4, 3) : new Thickness(12, 8, 12, 10);
        Rows.Spacing = mini ? 0 : 6;
        Rows.Margin = mini ? new Thickness(0) : new Thickness(0, 6, 0, 0);
        // 미니: 제목 표시줄(닫기 버튼)을 없애고 막대 영역 전체를 잡아 끌 수 있게
        _presenter.SetBorderAndTitleBar(true, !mini);
        SetTitleBar(mini ? Rows : DragArea);

        var r = mini ? _cfg.PipMiniRect : _cfg.PipRect;
        var p = AppWindow.Position;
        // 처음 전환할 때: 지금 위치에서 작업 표시줄 높이(48)로 / 일반 창 기본 크기로
        var rect = r is { Length: 4 } && IsOnScreen(r) ? new RectInt32(r[0], r[1], r[2], r[3])
            : mini ? new RectInt32(p.X, p.Y, Px(300), Px(48)) : new RectInt32(p.X, p.Y, Px(300), Px(130));
        if (keepPosition) rect = KeepInWorkArea(new RectInt32(p.X, p.Y, rect.Width, rect.Height));
        // 제목 표시줄 제거/복원이 뒤늦게 창 크기를 다시 계산하므로, 잠시 뒤 한 번 더 적용한다
        // ponytail: 150ms는 경험값. 느린 PC에서 크기가 어긋나면 늘릴 것
        AppWindow.MoveAndResize(rect);
        _resizeTimer ??= DispatcherQueue.CreateTimer();
        _resizeTimer.Stop();
        _resizeTimer.Interval = TimeSpan.FromMilliseconds(150);
        _resizeTimer.IsRepeating = false;
        _pendingRect = rect;
        _resizeTimer.Tick -= ResizeTick;
        _resizeTimer.Tick += ResizeTick;
        _resizeTimer.Start();
        if (_lastUpdate is var (results, last, at)) Update(results, last, at);
    }

    // 전역 단축키 Ctrl+Alt+U: 창에 포커스가 없어도 동작해야 하므로 RegisterHotKey + 창 서브클래싱
    delegate IntPtr SubclassProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam, UIntPtr id, UIntPtr data);
    [DllImport("comctl32.dll")] static extern bool SetWindowSubclass(IntPtr hWnd, SubclassProc proc, UIntPtr id, UIntPtr data);
    [DllImport("comctl32.dll")] static extern IntPtr DefSubclassProc(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr hWnd, int id, uint mods, uint vk);
    const uint WM_HOTKEY = 0x0312, MOD_ALT = 0x1, MOD_CONTROL = 0x2, MOD_NOREPEAT = 0x4000, VK_U = 0x55;
    SubclassProc? _subclass; // GC에 수거되지 않게 필드로 붙잡아 둔다

    void RegisterToggleHotkey()
    {
        _subclass = (h, msg, w, l, _, _) =>
        {
            // 네이티브 콜백 안에서 UI를 바꾸다 예외가 나면 프로세스가 즉시 종료되므로, 메시지 처리 후로 미룬다
            if (msg == WM_HOTKEY && w == 1) { DispatcherQueue.TryEnqueue(ToggleMini); return IntPtr.Zero; }
            return DefSubclassProc(h, msg, w, l);
        };
        SetWindowSubclass(_hwnd, _subclass, 1, 0);
        // ponytail: 다른 앱이 이미 쓰는 조합이면 등록 실패 → 버튼으로만 전환. 필요해지면 설정에서 키 변경 추가
        RegisterHotKey(_hwnd, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_U);
    }

    void Refresh_Click(object sender, RoutedEventArgs e) => RefreshRequested?.Invoke();

    // ---------- 설정 팔레트 ----------

    void TopMost_Toggled(object sender, RoutedEventArgs e)
    {
        if (!_ready) return;
        _presenter.IsAlwaysOnTop = _cfg.PipTopMost = TopMostSwitch.IsOn;
        _cfg.Save();
    }

    void Opacity_Changed(object sender, Microsoft.UI.Xaml.Controls.Primitives.RangeBaseValueChangedEventArgs e)
    {
        if (!_ready) return;
        _cfg.PipOpacity = (int)e.NewValue;
        ApplyOpacity();
        ScheduleSave(); // 드래그 중 매 틱마다 파일을 쓰지 않게
    }

    void BuildSwatches()
    {
        Swatches.Children.Clear();
        foreach (var (name, hex) in Palette)
        {
            var selected = hex == _cfg.PipColor;
            var b = new Button
            {
                Width = 26, Height = 26, Padding = new Thickness(0), CornerRadius = new CornerRadius(13),
                Background = hex == null ? new SolidColorBrush(Colors.Transparent) : Brush(hex),
                BorderThickness = new Thickness(selected ? 2.5 : 1),
                BorderBrush = selected ? (Brush)Application.Current.Resources["AccentFillColorDefaultBrush"] : Brush("#8a8a8a"),
                // 기본은 "배경 없음" 표시
                Content = hex == null ? new FontIcon { Glyph = "\uE894", FontSize = 11 } : null,
            };
            ToolTipService.SetToolTip(b, name);
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(b, name);
            b.Click += (_, _) =>
            {
                _cfg.PipColor = hex;
                _cfg.Save();
                ApplyColor();
                BuildSwatches(); // 선택 테두리 갱신
            };
            Swatches.Children.Add(b);
        }
    }

    static bool IsDark(string hex)
    {
        var c = Brush(hex).Color;
        return 0.299 * c.R + 0.587 * c.G + 0.114 * c.B < 128;
    }

    void ApplyColor()
    {
        var hex = _cfg.PipColor;
        Root.Background = hex == null ? null : Brush(hex);
        var theme = hex == null ? ElementTheme.Default : IsDark(hex) ? ElementTheme.Dark : ElementTheme.Light;
        Root.RequestedTheme = theme;
        // OS가 그리는 닫기 버튼: 배경은 투명하게, 글자색은 창 색에 맞춘다
        var tb = AppWindow.TitleBar;
        tb.ButtonBackgroundColor = tb.ButtonInactiveBackgroundColor = Colors.Transparent;
        tb.ButtonForegroundColor = theme switch
        {
            ElementTheme.Dark => Colors.White,
            ElementTheme.Light => Colors.Black,
            _ => null,
        };
    }

    [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll")] static extern int SetWindowLong(IntPtr hWnd, int nIndex, int dwNewLong);
    [DllImport("user32.dll")] static extern bool SetLayeredWindowAttributes(IntPtr hwnd, uint crKey, byte bAlpha, uint dwFlags);
    const int GWL_EXSTYLE = -20, WS_EX_LAYERED = 0x80000;
    const uint LWA_ALPHA = 0x2;

    /// 창 전체 투명도: layered 창 알파. 100%면 layered를 해제해 일반 창으로 되돌린다.
    void ApplyOpacity()
    {
        var ex = GetWindowLong(_hwnd, GWL_EXSTYLE);
        if (_cfg.PipOpacity >= 100)
        {
            SetWindowLong(_hwnd, GWL_EXSTYLE, ex & ~WS_EX_LAYERED);
            return;
        }
        SetWindowLong(_hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED);
        SetLayeredWindowAttributes(_hwnd, 0, (byte)(_cfg.PipOpacity * 255 / 100), LWA_ALPHA);
    }

    static SolidColorBrush Brush(string hex) => new(Color.FromArgb(0xff,
        Convert.ToByte(hex[1..3], 16), Convert.ToByte(hex[3..5], 16), Convert.ToByte(hex[5..7], 16)));

    /// results: 이번 조회 결과, last: 마지막 성공 값. 실패한 agent는 직전 값을 회색으로.
    (IReadOnlyDictionary<string, AgentResult>, IReadOnlyDictionary<string, AgentResult>, DateTime?)? _lastUpdate;

    public void Update(IReadOnlyDictionary<string, AgentResult> results,
                       IReadOnlyDictionary<string, AgentResult> last, DateTime? updatedAt)
    {
        _lastUpdate = (results, last, updatedAt); // 모드 전환 시 다시 그리기용
        var mini = _cfg.PipMini;
        Rows.Children.Clear();
        foreach (var (agent, name) in new[] { ("claude", "Claude"), ("codex", "Codex") })
        {
            if (!results.TryGetValue(agent, out var r)) continue;
            var usage = r.Usage ?? (last.TryGetValue(agent, out var l) ? l.Usage : null);
            var stale = r.Usage == null;
            foreach (var (label, w) in new[] { ("5h", usage?.FiveHour), ("week", usage?.Weekly) })
                Rows.Children.Add(Row($"{name} {label}", w ?? default, stale, mini));
            if (r.Error != null && !mini) // 미니에서는 오류 문구 대신 회색 막대로만 표시
                Rows.Children.Add(new TextBlock { Text = $"{name}: {r.Error}", Opacity = 0.7, FontSize = 11 });
        }
        if (Rows.Children.Count == 0)
            Rows.Children.Add(new TextBlock { Text = "트레이 메뉴에서 agent를 선택하세요", Opacity = 0.7 });
        Footer.Text = updatedAt is { } t ? $"갱신 {t:HH:mm:ss}" : "조회 중…";
    }

    static Grid Row(string label, UsageWindow w, bool stale, bool mini = false)
    {
        var font = mini ? 12.0 : 14.0;
        var color = Brush(stale ? UsageService.ColorUnknown : UsageService.ColorFor(w.Pct));
        var g = new Grid { ColumnSpacing = 8 };
        g.ColumnDefinitions.Add(new() { Width = new GridLength(mini ? 74 : 84) });
        g.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        g.ColumnDefinitions.Add(new() { Width = new GridLength(mini ? 34 : 40) });
        g.ColumnDefinitions.Add(new() { Width = new GridLength(mini ? 72 : 80) }); // 행마다 막대 길이가 같도록 고정 폭

        var bar = new ProgressBar { Value = w.Pct ?? 0, Maximum = 100, Foreground = color, VerticalAlignment = VerticalAlignment.Center };
        var pct = new TextBlock
        {
            Text = UsageService.FmtPct(w.Pct), Foreground = color, FontSize = font,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold, HorizontalAlignment = HorizontalAlignment.Right,
        };
        var reset = new TextBlock
        {
            Text = w.Reset is null ? "" : "↻" + UsageService.FmtTime(w.Reset),
            Opacity = 0.6, FontSize = mini ? 11 : 12, VerticalAlignment = VerticalAlignment.Center,
        };
        Grid.SetColumn(bar, 1);
        Grid.SetColumn(pct, 2);
        Grid.SetColumn(reset, 3);
        g.Children.Add(new TextBlock { Text = label, FontSize = font });
        g.Children.Add(bar);
        g.Children.Add(pct);
        g.Children.Add(reset);
        return g;
    }
}
