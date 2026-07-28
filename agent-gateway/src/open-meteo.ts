type OpenMeteoClientOptions = {
  fetch?: typeof fetch;
};

const WEATHER_CONDITIONS: Record<number, string> = {
  0: "晴朗",
  1: "大致晴朗",
  2: "局部多云",
  3: "阴天",
  45: "雾",
  48: "雾凇",
  51: "轻微毛毛雨",
  53: "毛毛雨",
  55: "强毛毛雨",
  56: "轻微冻毛毛雨",
  57: "强冻毛毛雨",
  61: "小雨",
  63: "中雨",
  65: "大雨",
  66: "轻微冻雨",
  67: "强冻雨",
  71: "小雪",
  73: "中雪",
  75: "大雪",
  77: "米雪",
  80: "阵雨",
  81: "较强阵雨",
  82: "强阵雨",
  85: "阵雪",
  86: "强阵雪",
  95: "雷暴",
  96: "雷暴伴轻微冰雹",
  99: "雷暴伴强冰雹",
};

export class OpenMeteoClient {
  readonly #fetch: typeof fetch;

  constructor(options: OpenMeteoClientOptions = {}) {
    this.#fetch = options.fetch ?? fetch;
  }

  /**
   * Fetches current conditions and a daily forecast for a named location.
   *
   * @param location Human-readable place name.
   * @param forecastDays Number of forecast days, clamped to one through seven.
   * @returns Normalized weather data suitable for a model tool result.
   */
  async weather(location: string, forecastDays: number) {
    const locationName = location.trim();
    if (!locationName) {
      throw new Error("Location is required");
    }

    const geocodingUrl = new URL(
      "https://geocoding-api.open-meteo.com/v1/search",
    );
    geocodingUrl.searchParams.set("name", locationName);
    geocodingUrl.searchParams.set("count", "1");
    geocodingUrl.searchParams.set("language", "zh");
    geocodingUrl.searchParams.set("format", "json");
    const geocodingResponse = await this.#fetch(geocodingUrl, {
      signal: AbortSignal.timeout(10_000),
    });
    if (!geocodingResponse.ok) {
      throw new Error(
        `Open-Meteo geocoding failed with status ${geocodingResponse.status}`,
      );
    }
    const geocodingBody = (await geocodingResponse.json()) as {
      results?: Array<{
        name?: string;
        admin1?: string;
        country?: string;
        latitude?: number;
        longitude?: number;
        timezone?: string;
      }>;
    };
    const place = geocodingBody.results?.[0];
    if (
      !place?.name ||
      !Number.isFinite(place.latitude) ||
      !Number.isFinite(place.longitude)
    ) {
      throw new Error(`Location not found: ${locationName}`);
    }

    const timezone = place.timezone || "auto";
    const weatherUrl = new URL("https://api.open-meteo.com/v1/forecast");
    weatherUrl.searchParams.set("latitude", String(place.latitude));
    weatherUrl.searchParams.set("longitude", String(place.longitude));
    weatherUrl.searchParams.set("timezone", timezone);
    weatherUrl.searchParams.set(
      "forecast_days",
      String(Math.min(Math.max(Math.trunc(forecastDays), 1), 7)),
    );
    weatherUrl.searchParams.set(
      "current",
      [
        "temperature_2m",
        "apparent_temperature",
        "relative_humidity_2m",
        "precipitation",
        "weather_code",
        "wind_speed_10m",
      ].join(","),
    );
    weatherUrl.searchParams.set(
      "daily",
      [
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_probability_max",
        "precipitation_sum",
        "wind_speed_10m_max",
      ].join(","),
    );
    const weatherResponse = await this.#fetch(weatherUrl, {
      signal: AbortSignal.timeout(10_000),
    });
    if (!weatherResponse.ok) {
      throw new Error(
        `Open-Meteo forecast failed with status ${weatherResponse.status}`,
      );
    }
    const weather = (await weatherResponse.json()) as {
      timezone?: string;
      current?: {
        time?: string;
        temperature_2m?: number;
        apparent_temperature?: number;
        relative_humidity_2m?: number;
        precipitation?: number;
        weather_code?: number;
        wind_speed_10m?: number;
      };
      daily?: {
        time?: string[];
        weather_code?: number[];
        temperature_2m_max?: number[];
        temperature_2m_min?: number[];
        precipitation_probability_max?: number[];
        precipitation_sum?: number[];
        wind_speed_10m_max?: number[];
      };
    };
    if (!weather.current || !weather.daily?.time) {
      throw new Error("Open-Meteo returned incomplete forecast data");
    }

    return {
      location: [place.name, place.admin1, place.country]
        .filter(Boolean)
        .join("，"),
      timezone: weather.timezone ?? timezone,
      current: {
        time: weather.current.time,
        condition:
          WEATHER_CONDITIONS[weather.current.weather_code ?? -1] ?? "未知",
        temperatureC: weather.current.temperature_2m,
        apparentTemperatureC: weather.current.apparent_temperature,
        humidityPercent: weather.current.relative_humidity_2m,
        precipitationMm: weather.current.precipitation,
        windSpeedKmh: weather.current.wind_speed_10m,
      },
      daily: weather.daily.time.map((date, index) => ({
        date,
        condition:
          WEATHER_CONDITIONS[weather.daily?.weather_code?.[index] ?? -1] ??
          "未知",
        temperatureMaxC: weather.daily?.temperature_2m_max?.[index],
        temperatureMinC: weather.daily?.temperature_2m_min?.[index],
        precipitationProbabilityPercent:
          weather.daily?.precipitation_probability_max?.[index],
        precipitationMm: weather.daily?.precipitation_sum?.[index],
        windSpeedMaxKmh: weather.daily?.wind_speed_10m_max?.[index],
      })),
      source: "https://open-meteo.com/",
    };
  }

  /**
   * Fetches current air-quality measurements for a named location.
   *
   * @param location Human-readable place name.
   * @returns Normalized air-quality data suitable for a model tool result.
   */
  async airQuality(location: string) {
    const locationName = location.trim();
    if (!locationName) {
      throw new Error("Location is required");
    }

    const geocodingUrl = new URL(
      "https://geocoding-api.open-meteo.com/v1/search",
    );
    geocodingUrl.searchParams.set("name", locationName);
    geocodingUrl.searchParams.set("count", "1");
    geocodingUrl.searchParams.set("language", "zh");
    geocodingUrl.searchParams.set("format", "json");
    const geocodingResponse = await this.#fetch(geocodingUrl, {
      signal: AbortSignal.timeout(10_000),
    });
    if (!geocodingResponse.ok) {
      throw new Error(
        `Open-Meteo geocoding failed with status ${geocodingResponse.status}`,
      );
    }
    const geocodingBody = (await geocodingResponse.json()) as {
      results?: Array<{
        name?: string;
        admin1?: string;
        country?: string;
        latitude?: number;
        longitude?: number;
        timezone?: string;
      }>;
    };
    const place = geocodingBody.results?.[0];
    if (
      !place?.name ||
      !Number.isFinite(place.latitude) ||
      !Number.isFinite(place.longitude)
    ) {
      throw new Error(`Location not found: ${locationName}`);
    }

    const timezone = place.timezone || "auto";
    const airQualityUrl = new URL(
      "https://air-quality-api.open-meteo.com/v1/air-quality",
    );
    airQualityUrl.searchParams.set("latitude", String(place.latitude));
    airQualityUrl.searchParams.set("longitude", String(place.longitude));
    airQualityUrl.searchParams.set("timezone", timezone);
    airQualityUrl.searchParams.set(
      "current",
      [
        "us_aqi",
        "pm2_5",
        "pm10",
        "carbon_monoxide",
        "nitrogen_dioxide",
        "ozone",
      ].join(","),
    );
    const airQualityResponse = await this.#fetch(airQualityUrl, {
      signal: AbortSignal.timeout(10_000),
    });
    if (!airQualityResponse.ok) {
      throw new Error(
        `Open-Meteo air quality failed with status ${airQualityResponse.status}`,
      );
    }
    const airQuality = (await airQualityResponse.json()) as {
      timezone?: string;
      current?: {
        time?: string;
        us_aqi?: number;
        pm2_5?: number;
        pm10?: number;
        carbon_monoxide?: number;
        nitrogen_dioxide?: number;
        ozone?: number;
      };
    };
    if (!airQuality.current) {
      throw new Error("Open-Meteo returned incomplete air-quality data");
    }
    const usAqi = airQuality.current.us_aqi;
    const category =
      usAqi === undefined
        ? "未知"
        : usAqi <= 50
          ? "优"
          : usAqi <= 100
            ? "中等"
            : usAqi <= 150
              ? "对敏感人群不健康"
              : usAqi <= 200
                ? "不健康"
                : usAqi <= 300
                  ? "非常不健康"
                  : "危险";

    return {
      location: [place.name, place.admin1, place.country]
        .filter(Boolean)
        .join("，"),
      timezone: airQuality.timezone ?? timezone,
      current: {
        time: airQuality.current.time,
        usAqi,
        category,
        pm25MicrogramsPerCubicMeter: airQuality.current.pm2_5,
        pm10MicrogramsPerCubicMeter: airQuality.current.pm10,
        carbonMonoxideMicrogramsPerCubicMeter:
          airQuality.current.carbon_monoxide,
        nitrogenDioxideMicrogramsPerCubicMeter:
          airQuality.current.nitrogen_dioxide,
        ozoneMicrogramsPerCubicMeter: airQuality.current.ozone,
      },
      source: "https://open-meteo.com/",
    };
  }
}
