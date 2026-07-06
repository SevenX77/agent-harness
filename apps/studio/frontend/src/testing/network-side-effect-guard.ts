import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios"

export interface RecordedBackendRequest {
  method: string
  url: string
  data: unknown
}

type BackendRouteResponse =
  | unknown
  | ((config: InternalAxiosRequestConfig) => unknown | Promise<unknown>)

export interface BackendRequestRecorder {
  adapter: AxiosAdapter
  readonly requests: readonly RecordedBackendRequest[]
  mark(): number
  requestsSince(mark: number): RecordedBackendRequest[]
}

export function createBackendRequestRecorder(
  routes: Record<string, BackendRouteResponse> = {},
): BackendRequestRecorder {
  const requests: RecordedBackendRequest[] = []

  const adapter: AxiosAdapter = async (config): Promise<AxiosResponse> => {
    const method = (config.method ?? "get").toUpperCase()
    const url = config.url ?? ""
    requests.push({ method, url, data: config.data })

    const route = routes[`${method} ${url}`] ?? routes[url] ?? {}
    const data = typeof route === "function" ? await route(config) : route
    return {
      data,
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    }
  }

  return {
    adapter,
    requests,
    mark: () => requests.length,
    requestsSince: (mark) => requests.slice(mark),
  }
}

export async function expectNoBackendRequestsDuring(
  recorder: BackendRequestRecorder,
  action: () => Promise<void> | void,
): Promise<void> {
  const mark = recorder.mark()
  await action()
  const unexpected = recorder.requestsSince(mark)
  if (unexpected.length > 0) {
    throw new Error(
      [
        "Expected UI interaction to be backend-silent, but it issued:",
        ...unexpected.map((request) => `- ${request.method} ${request.url}`),
      ].join("\n"),
    )
  }
}

