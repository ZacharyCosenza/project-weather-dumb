# NYC Proxy Weather Nowcaster

Why do we need historical temperature and pressure trends or complex physical models to predict the weather when we have access to the goings-on of the great people of New York City? That is what I am trying to answer with this repo. In this repo, correlation is causation. 

## Target

The label is derived from the Open-Meteo ERA5 archive — free, no API key, hourly resolution back to 1940. Each hourly row's ground-truth temperature is the raw `temperature_2m` field in Celsius, stored as `tgt_temp_c` and converted to °F at display time.

| Target | Derivation |
|---|---|
| `tgt_temp_c` | `temperature_2m` from ERA5 (°C float) |

![Target class balance](data/03_primary/plot_targets.png)

### Data

```
Open-Meteo ERA5      →  ground truth temperature (°C float)
NYISO grid load     ─┐
MTA ridership        ├─ lag-shifted features → XGBoost regressor → temperature (°F)
NYC 311 complaints   │
Motor vehicle crashes┘
```

The key constraint is that no direct weather data is used as a model input. Instead, proxy sources are used — things that *respond to weather* rather than measuring it. The model learns to invert that relationship.

**Publication lag:** Each source has a known delay between when an event happens and when the data is published. The lag shift `feature[t] = value[t - lag_days]` ensures the model only ever sees data that would have been available at the time of prediction.

---

## Features

<table>
<tr>
<td width="220" align="center"><img src="gifs/marv.gif" width="200" alt="NYISO grid load"></td>
<td valign="top"><strong><code>ft_nyiso_load_mw</code></strong> — Real-time electricity consumption for the NYC grid zone. High load in summer (AC) and winter (heating) is a direct temperature signal.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/power-lines-jump-rope.gif" width="200" alt="NYISO delta"></td>
<td valign="top"><strong><code>ft_nyiso_delta_3h</code></strong> — 3-hour change in grid load. Captures intra-day momentum — a rapid swing often means a weather front moving through.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/I_like_trains.gif" width="200" alt="MTA subway ridership"></td>
<td valign="top"><strong><code>ft_mta_subway</code></strong> — Daily subway entries system-wide. Rain and cold push riders underground; heat keeps them there. One of the strongest precipitation discriminators.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/c4mkd087lwlg1.gif" width="200" alt="MTA bus ridership"></td>
<td valign="top"><strong><code>ft_mta_bus</code></strong> — Daily bus boardings citywide. More weather-sensitive than subway: rain and cold spike ridership as pedestrians seek shelter.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/Amtrak_Snow_mo_Collision.gif" width="200" alt="LIRR ridership"></td>
<td valign="top"><strong><code>ft_mta_lirr</code></strong> — Daily Long Island Rail Road boardings. Snow events devastate LIRR operations — cancellations and suppressed demand show up immediately.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/frozen-freezing.gif" width="200" alt="311 heat complaints"></td>
<td valign="top"><strong><code>ft_311_heat</code></strong> — NYC 311 heat/inadequate heat complaints. Spikes in winter when building heat fails during cold snaps.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/snow-laughing.gif" width="200" alt="311 snow complaints"></td>
<td valign="top"><strong><code>ft_311_snow</code></strong> — NYC 311 snow/ice complaints. A lagged but reliable signal that snow fell recently and stuck around.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/crash-car.gif" width="200" alt="vehicle crashes"></td>
<td valign="top"><strong><code>ft_crashes_total</code></strong> — Total NYPD-reported motor vehicle crashes citywide. Volume drops sharply in heavy rain and snow as fewer people drive.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/slippery-dog.gif" width="200" alt="slippery road crashes"></td>
<td valign="top"><strong><code>ft_crashes_slippery</code></strong> — Crashes attributed to slippery pavement. A direct frozen-precipitation indicator that persists for days after a snow event.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/flood-simpsons.gif" width="200" alt="FloodNet street flood events"></td>
<td valign="top"><strong><code>ft_floodnet_events</code></strong> — Count of IoT flood sensor activations across NYC streets. Spikes only during heavy rain events.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/donald-trump-water.gif" width="200" alt="flood depth"></td>
<td valign="top"><strong><code>ft_floodnet_max_depth_in</code></strong> — Maximum street flood depth in inches recorded by FloodNet sensors. Intensity measure for the same events counted above.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/dog-cycling.gif" width="200" alt="bike count"></td>
<td valign="top"><strong><code>ft_ped_bike</code></strong> — DOT citywide bike sensor counts. Rain and cold suppress cycling sharply; hot days see a moderate dip too.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/seinfeld-walking.gif" width="200" alt="pedestrian count"></td>
<td valign="top"><strong><code>ft_ped_pedestrian</code></strong> — DOT pedestrian sensor counts. Heavy precipitation drives people indoors; extreme heat also suppresses foot traffic.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/speed-trap-police.gif" width="200" alt="congestion zone entries"></td>
<td valign="top"><strong><code>ft_cz_total</code></strong> — MTA Congestion Zone vehicle entries (Manhattan below 60th St, from Jan 2025). Traffic volume falls during storms.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/broke.gif" width="200" alt="evictions"></td>
<td valign="top"><strong><code>ft_evictions</code></strong> — NYC marshal-executed evictions. Weakly seasonal — fewer evictions in winter months correlates loosely with cold weather policy patterns.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/pizza-hungry.gif" width="200" alt="restaurant inspections"></td>
<td valign="top"><strong><code>ft_restaurant_inspections</code></strong> — DOHMH restaurant inspection volume. Inspectors go out less in bad weather, creating a mild precipitation proxy.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/spongebob.gif" width="200" alt="restaurant critical violations"></td>
<td valign="top"><strong><code>ft_restaurant_critical</code></strong> — Critical violations found during inspections. Correlated with inspection volume but adds severity signal.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/let's-go-mets-major-league-baseball.gif" width="200" alt="Mets win pct"></td>
<td valign="top"><strong><code>ft_mets_win_pct</code></strong> — Mets season win percentage (NaN off-season). Games are called for rain; win rate dips correlate loosely with bad-weather stretches.</td>
</tr>
<tr>
<td width="220" align="center"><img src="gifs/yankees-seinfeld.gif" width="200" alt="Yankees win pct"></td>
<td valign="top"><strong><code>ft_yankees_win_pct</code></strong> — Yankees season win percentage (NaN off-season). Same logic as Mets — a second independent baseball-weather proxy.</td>
</tr>
</table>

Daily sources are reindexed to hourly by holding each day's value constant across all 24 hours, then the lag shift is applied on the hourly index.

![Features over time](data/03_primary/plot_features_time.png)

![Feature distributions by precipitation class](data/03_primary/plot_distributions.png)

![Feature × target correlations](data/03_primary/plot_correlations.png)

---

## Results

The model is evaluated against two holdout sets: a temporal test set (Jul 2024–present, production-realistic) and a random 10% sample across all time (an upper bound). The temporal test is the honest number — it measures performance on future data the model has never seen. Metrics are RMSE, MAE, and R².

![Model evaluation — RMSE / MAE / R²](data/03_primary/plot_metrics.png)

SHAP values explain which features drove each prediction. The beeswarm plot shows how feature values (color) push the temperature prediction up or down — high NYISO load in summer, for example, correlates with high SHAP values for `ft_nyiso_load_mw`.

![SHAP — temperature model](data/03_primary/shap_temp.png)

## Docker Setup

Install Docker Engine and the Compose plugin from Docker's official apt repo:

```bash
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

Add your user to the `docker` group so you can run Docker without `sudo`:

```bash
sudo usermod -aG docker $USER
newgrp docker   # applies to the current shell; log out/in to make it permanent
```

Verify:

```bash
docker compose version
```

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Train the model

Fetches all data sources, merges them, and trains the temperature regressor. On first run it downloads ~4 years of hourly data — expect 3–5 minutes.

```bash
kedro run
```

Outputs written to `data/03_primary/`: trained model, evaluation plots, SHAP plot.

### 3. Run inference

Loads the trained models and generates a prediction for the most recent available hour.

```bash
kedro run --pipeline inference
```

Output: `data/03_primary/predictions.json`

### 4. Launch the website

```bash
streamlit run app/app.py
```

Opens at `http://localhost:8501`. Shows the current temperature prediction in °F with SHAP feature contributions.

To run the site persistently in the background (survives closing the terminal):

```bash
nohup streamlit run app/app.py >> logs/streamlit.log 2>&1 &
```

To stop it:

```bash
pkill -f "streamlit run"
```

### 5. Schedule automatic refresh

Run via `crontab -e`. Use absolute paths throughout — cron runs without your shell environment.

```
# Hourly: fast inference (at :05 past the hour — gives NYISO time to publish)
5 * * * * docker exec weather-pipeline /app/run_inference_only.sh >> /home/cosenzac/code/project-weather-dumb/logs/cron.log 2>&1

# Nightly: full retrain at 02:00
0 2 * * * docker exec weather-pipeline /app/run_pipeline.sh >> /home/cosenzac/code/project-weather-dumb/logs/cron.log 2>&1

# Rotate cron log weekly, keep 4 weeks
0 0 * * 0 mv /home/cosenzac/code/project-weather-dumb/logs/cron.log /home/cosenzac/code/project-weather-dumb/logs/cron.log.$(date +\%Y\%W) && touch /home/cosenzac/code/project-weather-dumb/logs/cron.log

# Monitor: check predictions freshness + web container every 30 min
*/30 * * * * cd /home/cosenzac/code/project-weather-dumb && .venv/bin/python -m weather.monitor check >> /home/cosenzac/code/project-weather-dumb/logs/monitor.log 2>&1

# Monitor: startup email with ngrok URL (60s delay lets Docker + ngrok settle after boot)
@reboot sleep 60 && cd /home/cosenzac/code/project-weather-dumb && .venv/bin/python -m weather.monitor startup >> /home/cosenzac/code/project-weather-dumb/logs/monitor.log 2>&1
```

**Common gotchas:**
- The `logs/` directory is created by Docker and will be owned by `root` — fix once with `sudo chown $USER logs/`
- The user must be in the `docker` group (`sudo usermod -aG docker $USER`, then log out/in) — otherwise all `docker exec` cron entries fail silently
- Use `.venv/bin/python` explicitly — cron has no knowledge of activated virtualenvs

Watch the logs:
```bash
tail -f logs/cron.log      # pipeline runs
tail -f logs/monitor.log   # health checks and startup emails
```

---

## Secrets & Environment

All secrets live in `.env` at the project root (do not commit). Docker Compose loads it automatically; `monitor.py` reads it directly.

| Variable | Used by | Description |
|---|---|---|
| `NGROK_AUTHTOKEN` | `docker-compose.yml` → `ngrok` service | ngrok account token for the public tunnel |
| `ALERT_SMTP_PASSWORD` | `monitor.py` | Gmail [app password](https://myaccount.google.com/apppasswords) for alert emails |

```bash
# .env (template — copy and fill in values, never commit this file)
NGROK_AUTHTOKEN=your-ngrok-token
ALERT_SMTP_PASSWORD=xxxx xxxx xxxx xxxx
```

Alert email addresses (`email_from`, `email_to`) are set in `conf/base/parameters.yml` — not in `.env` since they are not secrets.

---

## Monitoring

`src/weather/monitor/monitor.py` watches the running system and sends Gmail alerts. Invoked by cron; can also be run manually.

### Modes

| Command | Triggered by | What it does |
|---|---|---|
| `.venv/bin/python -m weather.monitor startup` | `@reboot` cron (60s delay) | Polls the ngrok local API until a public URL is confirmed (up to 3 min), then emails it with container status and predictions age. Skips the email entirely if ngrok never comes up — check `logs/ngrok.log` via `docker compose logs ngrok`. |
| `.venv/bin/python -m weather.monitor check` | `*/30` cron | Emails an alert if `predictions.json` is older than `stale_threshold_hours` (default: 3h) or if the `weather-web` container is not running. Prints to stdout if all is well. |
| `.venv/bin/python -m weather.monitor test` | Manual | Sends a test email to verify SMTP is working. |

Run any mode manually from the project root:
```bash
cd /home/cosenzac/code/project-weather-dumb
.venv/bin/python -m weather.monitor startup   # get the ngrok URL emailed now
.venv/bin/python -m weather.monitor check     # run a health check now
.venv/bin/python -m weather.monitor test      # verify SMTP config
```

### Configuration

Email addresses live in `conf/base/parameters.yml` under `alert:`:

```yaml
alert:
  email_from: you@gmail.com
  email_to:   [you@gmail.com]
  stale_threshold_hours: 3
  web_container: weather-web
```

The SMTP password is read from `.env` first, falling back to the `ALERT_SMTP_PASSWORD` environment variable.

### Why startup email requires a reboot

The `@reboot` cron only fires on system boot. Docker containers restart automatically (`restart: unless-stopped`), so on reboot the sequence is:

1. Docker daemon starts → containers come back up
2. 60s sleep → monitor starts
3. Monitor polls `localhost:4040/api/tunnels` every 3s for up to 3 min until ngrok reports a URL
4. Email sent with confirmed public URL

If you restart Docker manually (e.g. after pulling changes), trigger the startup email yourself:
```bash
.venv/bin/python -m weather.monitor startup
```

---

## Updating After a Code Change

```bash
git pull

# Rebuild the image (required whenever src/, conf/, or requirements.txt change)
docker compose build

# Restart containers with the new image
docker compose up -d

# Run the full pipeline immediately rather than waiting for the 2am cron
docker exec weather-pipeline /app/run_pipeline.sh

# Email yourself the (unchanged) ngrok URL to confirm everything is back up
.venv/bin/python -m weather.monitor startup
```

`data/` and `logs/` are bind-mounted and survive rebuilds — trained models and historical data are not lost.

---