import { isValidElement } from "react"
import { describe, expect, it, vi } from "vitest"
import { Toaster } from "./sonner"

const sonnerMock = vi.hoisted(() => vi.fn(() => null))

vi.mock("sonner", () => ({
  Toaster: sonnerMock,
}))

vi.mock("@/store/themeStore", () => ({
  useThemeValue: () => "dark",
}))

vi.mock("lucide-react", () => ({
  CircleCheckIcon: () => <i data-icon="circle-check" />,
  InfoIcon: () => <i data-icon="info" />,
  TriangleAlertIcon: () => <i data-icon="triangle-alert" />,
  OctagonXIcon: () => <i data-icon="octagon-x" />,
  Loader2Icon: () => <i data-icon="loader" />,
  CheckCircle: () => <i data-icon="check-circle" />,
  Info: () => <i data-icon="legacy-info" />,
  AlertTriangle: () => <i data-icon="alert-triangle" />,
  XCircle: () => <i data-icon="x-circle" />,
  Loader2: () => <i data-icon="legacy-loader" />,
}))

describe("Toaster", () => {
  it("uses the shadcn sonner icon set while preserving the app z-index class", () => {
    const element = Toaster({})
    if (!isValidElement(element)) {
      throw new Error("Toaster did not return a React element")
    }
    const props = element.props as {
      theme: string
      className: string
      toastOptions: { classNames: { toast: string } }
      icons: Record<string, { type: () => React.ReactElement }>
    }

    expect(props.theme).toBe("dark")
    expect(props.className).toBe("toaster group z-toast")
    expect(props.toastOptions.classNames.toast).toBe("cn-toast")
    expect(isValidElement(props.icons.error)).toBe(true)
    expect(props.icons.error.type()).toEqual(<i data-icon="octagon-x" />)
    expect(props.icons.success.type()).toEqual(<i data-icon="circle-check" />)
  })
})
