type FrankfurterClientOptions = {
  fetch?: typeof fetch;
};

export class FrankfurterClient {
  readonly #fetch: typeof fetch;

  constructor(options: FrankfurterClientOptions = {}) {
    this.#fetch = options.fetch ?? fetch;
  }

  /**
   * Converts an amount using the latest Frankfurter reference rate.
   *
   * @param amount Numeric amount to convert.
   * @param from Source ISO 4217 currency code.
   * @param to Target ISO 4217 currency code.
   * @returns Conversion details and reference-rate attribution.
   */
  async convert(amount: number, from: string, to: string) {
    if (!Number.isFinite(amount)) {
      throw new Error("Amount must be a finite number");
    }
    const sourceCurrency = from.trim().toUpperCase();
    const targetCurrency = to.trim().toUpperCase();
    if (
      !/^[A-Z]{3}$/u.test(sourceCurrency) ||
      !/^[A-Z]{3}$/u.test(targetCurrency)
    ) {
      throw new Error("Currency code must contain exactly three letters");
    }

    const url = new URL(
      `https://api.frankfurter.dev/v2/rate/${sourceCurrency}/${targetCurrency}`,
    );
    const response = await this.#fetch(url, {
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) {
      throw new Error(
        `Frankfurter request failed with status ${response.status}`,
      );
    }
    const body = (await response.json()) as {
      date?: string;
      base?: string;
      quote?: string;
      rate?: number;
    };
    if (!Number.isFinite(body.rate)) {
      throw new Error("Frankfurter returned an invalid exchange rate");
    }
    const rate = body.rate as number;

    return {
      amount,
      from: body.base ?? sourceCurrency,
      to: body.quote ?? targetCurrency,
      rate,
      convertedAmount: Math.round(amount * rate * 1_000_000) / 1_000_000,
      date: body.date,
      note: "欧洲央行参考汇率；不代表银行或支付平台的实时成交价。",
      source: "https://frankfurter.dev/",
    };
  }
}
