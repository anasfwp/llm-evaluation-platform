import { ApiError, api } from "../api/client";

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("builds query strings and skips empty values", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, limit: 25, offset: 0 })));
    await api.listRuns({ project_id: "p1", status: "", limit: 25 });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/v1/runs?project_id=p1&limit=25");
  });

  it("unpacks the error envelope", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "VALIDATION_ERROR",
            message: "Request validation failed",
            details: [{ field: "metrics[0].name", message: "unknown metric" }],
            request_id: "req-1",
          },
        }),
        { status: 422 },
      ),
    );
    const error = await api.getRun("x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(422);
    expect(apiError.details[0]!.field).toBe("metrics[0].name");
    expect(apiError.requestId).toBe("req-1");
  });

  it("reports an unreachable backend clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.listMetrics()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});
