"""Long-running scheduler (one container).  python -m src.live.scheduler

  every 30 min : live weather -> refresh live_risk
  every 15 min : live traffic (only if TOMTOM_KEY set)
  monthly      : validation gate -> hotspots -> EB -> multipliers -> train -> refresh   (RETRAIN_CRON)
"""
import logging
import os
import subprocess
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scheduler")


def run(module, *args):
    log.info("running %s", module)
    return subprocess.run([sys.executable, "-m", module, *args], check=True)


def safe(fn):
    def wrapper():
        try:
            fn()
        except Exception:
            log.exception("job %s failed", fn.__name__)
    wrapper.__name__ = fn.__name__
    return wrapper


@safe
def weather_job():
    run("src.live.weather_live")
    run("src.live.refresh")


@safe
def traffic_job():
    run("src.live.traffic_live")


@safe
def retrain_job():
    run("src.validation")                      # aborts the retrain if data-quality errors are found
    for m in ("src.models.hotspots", "src.models.empirical_bayes", "src.models.multipliers", "src.models.train",
              "src.live.refresh"):
        run(m)


def main():
    s = BlockingScheduler(timezone=os.getenv("TIMEZONE", "Asia/Kolkata"))
    s.add_job(weather_job, "interval", minutes=30, id="weather", max_instances=1)
    if os.getenv("TOMTOM_KEY"):
        s.add_job(traffic_job, "interval", minutes=15, id="traffic", max_instances=1)
    s.add_job(retrain_job, CronTrigger.from_crontab(os.getenv("RETRAIN_CRON", "0 2 1 * *")), id="retrain",
              max_instances=1)
    weather_job()                              # warm start
    log.info("scheduler started")
    s.start()


if __name__ == "__main__":
    main()
