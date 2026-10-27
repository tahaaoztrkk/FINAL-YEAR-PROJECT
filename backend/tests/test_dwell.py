"""Dwell seçim mantığının testleri.

Midas touch ve titreme toleransı burada korunuyor: ikisi de kullanıcı
çalışmasında doğrudan hata oranına yansır.
"""

from __future__ import annotations

from gaze_aac.gaze.dwell import DwellDetector
from gaze_aac.schemas.gaze import GazeTarget

TARGET = GazeTarget(id="k1", x=0.1, y=0.1, width=0.3, height=0.3, label="A")
OTHER = GazeTarget(id="k2", x=0.6, y=0.1, width=0.3, height=0.3, label="B")


def _detector(dwell_ms: int = 700, grace: int = 150, refractory: int = 0) -> DwellDetector:
    detector = DwellDetector(dwell_ms=dwell_ms, cancel_grace_ms=grace, refractory_ms=refractory)
    detector.set_targets([TARGET, OTHER])
    return detector


class TestSelection:
    def test_selects_after_dwell_time(self) -> None:
        detector = _detector(dwell_ms=500)
        detector.update(0.2, 0.2, 0.0)  # ilk örnek yalnızca saati kurar

        event = detector.update(0.2, 0.2, 0.3)
        assert not event.selected
        assert 0.5 < event.progress < 0.7

        event = detector.update(0.2, 0.2, 0.6)
        assert event.selected
        assert event.target_id == "k1"

    def test_no_selection_outside_any_target(self) -> None:
        detector = _detector(dwell_ms=300)
        detector.update(0.5, 0.9, 0.0)
        event = detector.update(0.5, 0.9, 1.0)
        assert not event.selected
        assert event.target_id is None

    def test_progress_resets_when_moving_to_another_target(self) -> None:
        detector = _detector(dwell_ms=500)
        detector.update(0.2, 0.2, 0.0)
        detector.update(0.2, 0.2, 0.4)  # k1 üstünde %80

        event = detector.update(0.7, 0.2, 0.5)  # k2'ye geç
        assert event.target_id == "k2"
        assert event.progress < 0.3


class TestGracePeriod:
    def test_short_glance_away_keeps_progress(self) -> None:
        """Bakış tahmininin titremesi hedefin kenarında dolaşır;
        her sapmada sıfırlanırsa seçim hiç tamamlanmaz."""
        detector = _detector(dwell_ms=500, grace=200)
        detector.update(0.2, 0.2, 0.0)
        detector.update(0.2, 0.2, 0.4)

        away = detector.update(0.5, 0.9, 0.45)  # 50 ms dışarıda
        assert away.progress > 0.5  # ilerleme korundu

        back = detector.update(0.2, 0.2, 0.55)
        assert back.selected

    def test_long_look_away_cancels(self) -> None:
        detector = _detector(dwell_ms=500, grace=100)
        detector.update(0.2, 0.2, 0.0)
        detector.update(0.2, 0.2, 0.4)

        detector.update(0.5, 0.9, 0.9)  # 500 ms dışarıda
        event = detector.update(0.2, 0.2, 1.0)
        assert not event.selected
        assert event.progress < 0.3


class TestRefractory:
    def test_no_double_selection_right_after_one(self) -> None:
        """Seçimden sonra kullanıcının bakışını çekmesi zaman alır;
        bu sürede ikinci seçim tetiklenmemeli."""
        detector = _detector(dwell_ms=200, refractory=300)
        detector.update(0.2, 0.2, 0.0)
        assert detector.update(0.2, 0.2, 0.25).selected

        during = detector.update(0.2, 0.2, 0.35)
        assert not during.selected


class TestExitLock:
    """Seçimden sonra bakış hedeften ayrılmadan yeni seçim yapılamaz.

    Süre temelli bekleme tek başına yetmiyor: hiç kıpırdamayan bir bakış,
    süre dolar dolmaz aynı noktayı yeniden seçer. Ekran düzeni seçimden
    sonra değiştiği için (grup → harf) kullanıcı tek harf yazmak isterken
    üç tuşa basmış olur.
    """

    def test_staying_on_target_does_not_select_again(self) -> None:
        detector = _detector(dwell_ms=200, refractory=0)
        detector.update(0.2, 0.2, 0.0)
        assert detector.update(0.2, 0.2, 0.25).selected

        # Bakış kıpırdamıyor: uzun süre beklese de ikinci seçim olmamalı.
        for step in range(2, 20):
            event = detector.update(0.2, 0.2, step * 0.25)
            assert not event.selected
            assert event.progress == 0.0

    def test_selects_again_after_leaving_and_returning(self) -> None:
        detector = _detector(dwell_ms=200, refractory=0)
        detector.update(0.2, 0.2, 0.0)
        assert detector.update(0.2, 0.2, 0.25).selected

        detector.update(0.7, 0.2, 0.30)  # başka hedefe geç: kilit açılır
        detector.update(0.2, 0.2, 0.35)  # geri dön
        assert detector.update(0.2, 0.2, 0.60).selected

    def test_lock_survives_layout_change(self) -> None:
        """Seçimden sonra düzen değişir ve aynı hücrede başka tuş durur.

        Kilit düzen değişikliğinde temizlenseydi, kıpırdamayan bakış o yeni
        tuşu da seçerdi — zincirleme seçimin tam olarak çıktığı yer burası.
        """
        detector = _detector(dwell_ms=200, refractory=0)
        detector.update(0.2, 0.2, 0.0)
        assert detector.update(0.2, 0.2, 0.25).selected

        # Arayüz yeni düzeni gönderir; aynı konumda farklı kimlikli tuş var.
        replacement = GazeTarget(id="yeni", x=0.1, y=0.1, width=0.3, height=0.3, label="S")
        detector.set_targets([replacement, OTHER])

        for step in range(2, 12):
            assert not detector.update(0.2, 0.2, step * 0.25).selected

    def test_leaving_to_empty_space_also_unlocks(self) -> None:
        detector = _detector(dwell_ms=200, refractory=0)
        detector.update(0.2, 0.2, 0.0)
        assert detector.update(0.2, 0.2, 0.25).selected

        detector.update(0.5, 0.9, 0.30)  # boşluğa bak
        detector.update(0.2, 0.2, 0.35)
        assert detector.update(0.2, 0.2, 0.60).selected


class TestHitTest:
    def test_smaller_target_wins_when_overlapping(self) -> None:
        big = GazeTarget(id="buyuk", x=0.0, y=0.0, width=1.0, height=1.0)
        small = GazeTarget(id="kucuk", x=0.4, y=0.4, width=0.2, height=0.2)
        detector = DwellDetector(dwell_ms=100)
        detector.set_targets([big, small])

        detector.update(0.5, 0.5, 0.0)
        event = detector.update(0.5, 0.5, 0.05)
        assert event.target_id == "kucuk"

    def test_changing_targets_clears_progress(self) -> None:
        detector = _detector(dwell_ms=500)
        detector.update(0.2, 0.2, 0.0)
        detector.update(0.2, 0.2, 0.4)

        detector.set_targets([TARGET])  # düzen değişti
        event = detector.update(0.2, 0.2, 0.45)
        assert event.progress < 0.3


class TestGazeTarget:
    def test_contains(self) -> None:
        assert TARGET.contains(0.2, 0.2)
        assert not TARGET.contains(0.5, 0.5)

    def test_center(self) -> None:
        cx, cy = TARGET.center
        assert abs(cx - 0.25) < 1e-9
        assert abs(cy - 0.25) < 1e-9


class TestManualLock:
    def test_click_locks_target_against_dwell(self) -> None:
        """Tıklanan tuşun üstünde duran imleç, tuşu dwell ile bir daha seçmez."""
        detector = _detector(dwell_ms=200)
        detector.update(0.2, 0.2, 0.0)
        detector.lock("k1")

        for step in range(1, 10):
            assert not detector.update(0.2, 0.2, step * 0.25).selected

        detector.update(0.7, 0.2, 2.6)  # başka hedefe geç: kilit açılır
        detector.update(0.2, 0.2, 2.7)
        assert detector.update(0.2, 0.2, 3.0).selected
