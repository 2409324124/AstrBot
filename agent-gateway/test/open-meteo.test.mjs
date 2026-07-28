import assert from "node:assert/strict";
import test from "node:test";

import { OpenMeteoClient } from "../src/open-meteo.ts";

test("Open-Meteo resolves a Chinese location and returns current plus seven-day weather", async () => {
  const urls = [];
  const client = new OpenMeteoClient({
    fetch: async (input) => {
      const url = new URL(input);
      urls.push(url);
      if (url.hostname === "geocoding-api.open-meteo.com") {
        return new Response(JSON.stringify({
          results: [{
            name: "广州",
            admin1: "广东",
            country: "中国",
            latitude: 23.1167,
            longitude: 113.25,
            timezone: "Asia/Shanghai"
          }]
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response(JSON.stringify({
        timezone: "Asia/Shanghai",
        current: {
          time: "2026-07-29T14:00",
          temperature_2m: 32.4,
          apparent_temperature: 37.2,
          relative_humidity_2m: 68,
          precipitation: 0,
          weather_code: 1,
          wind_speed_10m: 9.8
        },
        daily: {
          time: ["2026-07-29", "2026-07-30"],
          weather_code: [1, 80],
          temperature_2m_max: [34, 33],
          temperature_2m_min: [27, 26],
          precipitation_probability_max: [20, 70],
          precipitation_sum: [0, 4.2],
          wind_speed_10m_max: [16, 19]
        }
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
  });

  const report = await client.weather("广州", 7);

  assert.equal(urls[0].searchParams.get("name"), "广州");
  assert.equal(urls[0].searchParams.get("language"), "zh");
  assert.equal(urls[1].searchParams.get("forecast_days"), "7");
  assert.equal(urls[1].searchParams.get("timezone"), "Asia/Shanghai");
  assert.deepEqual(report, {
    location: "广州，广东，中国",
    timezone: "Asia/Shanghai",
    current: {
      time: "2026-07-29T14:00",
      condition: "大致晴朗",
      temperatureC: 32.4,
      apparentTemperatureC: 37.2,
      humidityPercent: 68,
      precipitationMm: 0,
      windSpeedKmh: 9.8
    },
    daily: [{
      date: "2026-07-29",
      condition: "大致晴朗",
      temperatureMaxC: 34,
      temperatureMinC: 27,
      precipitationProbabilityPercent: 20,
      precipitationMm: 0,
      windSpeedMaxKmh: 16
    }, {
      date: "2026-07-30",
      condition: "阵雨",
      temperatureMaxC: 33,
      temperatureMinC: 26,
      precipitationProbabilityPercent: 70,
      precipitationMm: 4.2,
      windSpeedMaxKmh: 19
    }],
    source: "https://open-meteo.com/"
  });
});

test("Open-Meteo returns current air quality for a named location", async () => {
  const urls = [];
  const client = new OpenMeteoClient({
    fetch: async (input) => {
      const url = new URL(input);
      urls.push(url);
      if (url.hostname === "geocoding-api.open-meteo.com") {
        return new Response(JSON.stringify({
          results: [{
            name: "广州",
            admin1: "广东",
            country: "中国",
            latitude: 23.1167,
            longitude: 113.25,
            timezone: "Asia/Shanghai"
          }]
        }), { status: 200 });
      }
      return new Response(JSON.stringify({
        timezone: "Asia/Shanghai",
        current: {
          time: "2026-07-29T14:00",
          us_aqi: 82,
          pm2_5: 28.4,
          pm10: 46.1,
          carbon_monoxide: 412,
          nitrogen_dioxide: 23.8,
          ozone: 91.2
        }
      }), { status: 200 });
    }
  });

  const report = await client.airQuality("广州");

  assert.equal(urls[1].hostname, "air-quality-api.open-meteo.com");
  assert.equal(urls[1].searchParams.get("timezone"), "Asia/Shanghai");
  assert.deepEqual(report, {
    location: "广州，广东，中国",
    timezone: "Asia/Shanghai",
    current: {
      time: "2026-07-29T14:00",
      usAqi: 82,
      category: "中等",
      pm25MicrogramsPerCubicMeter: 28.4,
      pm10MicrogramsPerCubicMeter: 46.1,
      carbonMonoxideMicrogramsPerCubicMeter: 412,
      nitrogenDioxideMicrogramsPerCubicMeter: 23.8,
      ozoneMicrogramsPerCubicMeter: 91.2
    },
    source: "https://open-meteo.com/"
  });
});
