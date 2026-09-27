from futures_analyzer.refresh import RefreshJob


def test_job_runs_once_at_a_time_and_keeps_log():
    calls = []

    def fake_refresh(engine, log):
        calls.append(engine)
        log("adım 1")
        return ["makro: ağ hatası"]

    job = RefreshJob(lambda: "db", refresh=fake_refresh)

    assert job.run_now() is True
    status = job.status()
    assert calls == ["db"]
    assert status["log"] == ["adım 1"]
    assert status["errors"] == ["makro: ağ hatası"]
    assert status["running"] is False and status["last_finished"] is not None


def test_job_survives_unexpected_error():
    def broken(engine, log):
        raise RuntimeError("beklenmedik")

    job = RefreshJob(lambda: "db", refresh=broken)
    job.run_now()

    assert job.status()["errors"] == ["beklenmedik"]
    assert job.running is False


def test_second_start_is_ignored_while_running():
    job = RefreshJob(lambda: "db", refresh=lambda engine, log: [])
    job.running = True

    assert job.start() is False
    assert job.run_now() is False
