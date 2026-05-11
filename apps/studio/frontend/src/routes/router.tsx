import { createHashRouter, Navigate } from 'react-router-dom'
import Home from './home'
import Root, { RootErrorBoundary } from './root'
import Debug from './skill/debug'
import Edit from './skill/edit'
import Eval from './skill/eval'
import SkillLayout from './skill/layout'
import Predict from './skill/predict'
import Run from './skill/run'

function SettingsPlaceholder() {
  return <div>TODO settings.tsx</div>
}

export const router = createHashRouter([
  {
    path: '/',
    element: <Root />,
    errorElement: <RootErrorBoundary />,
    children: [
      {
        index: true,
        element: <Home />,
      },
      {
        path: 'skill/:skillId',
        element: <SkillLayout />,
        children: [
          {
            index: true,
            element: <Navigate to="edit" replace />,
          },
          {
            path: 'edit',
            element: <Edit />,
          },
          {
            path: 'predict',
            element: <Predict />,
          },
          {
            path: 'run',
            element: <Run />,
          },
          {
            path: 'run/:runId',
            element: <Run />,
          },
          {
            path: 'debug',
            element: <Debug />,
          },
          {
            path: 'eval',
            element: <Eval />,
          },
        ],
      },
      {
        path: 'settings',
        element: <SettingsPlaceholder />,
      },
    ],
  },
])

export default router
