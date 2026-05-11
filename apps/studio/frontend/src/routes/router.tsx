import { lazy, Suspense } from 'react'
import { createHashRouter, Navigate } from 'react-router-dom'
import Home, { homeLoader } from './home'
import Root, { RootErrorBoundary } from './root'

const Settings = lazy(() => import('./settings'))
const SkillLayout = lazy(() => import('./skill/layout'))
const Edit = lazy(() => import('./skill/edit'))
const Predict = lazy(() => import('./skill/predict'))
const Run = lazy(() => import('./skill/run'))
const Debug = lazy(() => import('./skill/debug'))
const Eval = lazy(() => import('./skill/eval'))

function routeElement(element: React.ReactNode) {
  return (
    <Suspense
      fallback={(
        <div className="grid min-h-screen place-items-center bg-background text-sm text-muted-foreground">
          Loading Studio view...
        </div>
      )}
    >
      {element}
    </Suspense>
  )
}

export const router = createHashRouter([
  {
    path: '/',
    element: <Root />,
    errorElement: <RootErrorBoundary />,
    children: [
      {
        index: true,
        element: routeElement(<Home />),
        loader: homeLoader,
      },
      {
        path: 'skill/:skillId',
        element: routeElement(<SkillLayout />),
        children: [
          {
            index: true,
            element: <Navigate to="edit" replace />,
          },
          {
            path: 'edit',
            element: routeElement(<Edit />),
          },
          {
            path: 'predict',
            element: routeElement(<Predict />),
          },
          {
            path: 'run',
            element: routeElement(<Run />),
          },
          {
            path: 'run/:runId',
            element: routeElement(<Run />),
          },
          {
            path: 'debug',
            element: routeElement(<Debug />),
          },
          {
            path: 'eval',
            element: routeElement(<Eval />),
          },
        ],
      },
      {
        path: 'settings',
        element: routeElement(<Settings />),
      },
    ],
  },
])

export default router
