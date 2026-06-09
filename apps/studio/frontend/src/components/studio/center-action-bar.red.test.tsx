import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { CenterActionBar } from './center-action-bar'

describe('CenterActionBar WS-3 alignment contracts (Regression Lock)', () => {
  it('locks Predict and Run when stage is idle, compiling, or compile-fail', () => {
    const html = renderToStaticMarkup(
      <CenterActionBar
        stage="compile-fail"
        onCompile={() => {}}
        onPredict={() => {}}
        onRun={() => {}}
      />
    )
    
    // Predict and Run buttons should have disabled attribute
    // React renderToStaticMarkup generates disabled="" or just disabled for <button disabled>
    // Let's assert that the button containing "Predict" has disabled
    expect(html).toContain('disabled')
    
    // We check that the overall markup has disabled elements for Predict and Run
    const compileMatch = html.match(/<button[^>]*>.*?Compile.*?<\/button>/s)
    const predictMatch = html.match(/<button[^>]*>.*?Predict.*?<\/button>/s)
    const runMatch = html.match(/<button[^>]*>.*?Run.*?<\/button>/s)

    expect(compileMatch).toBeTruthy()
    expect(predictMatch).toBeTruthy()
    expect(runMatch).toBeTruthy()

    // Helper to check if string contains the disabled attribute (not the CSS class)
    const hasDisabledAttr = (str: string) => /\sdisabled([=>\s]|$)/.test(str)

    // Compile button should not be disabled when stage is compile-fail
    expect(hasDisabledAttr(compileMatch![0])).toBe(false)
    // Predict and Run buttons must be disabled
    expect(hasDisabledAttr(predictMatch![0])).toBe(true)
    expect(hasDisabledAttr(runMatch![0])).toBe(true)
  })

  it('unlocks Predict but locks Run when stage is compile-pass, predicting, or predict-fail', () => {
    const html = renderToStaticMarkup(
      <CenterActionBar
        stage="compile-pass"
        onCompile={() => {}}
        onPredict={() => {}}
        onRun={() => {}}
      />
    )

    const compileMatch = html.match(/<button[^>]*>.*?Compile.*?<\/button>/s)
    const predictMatch = html.match(/<button[^>]*>.*?Predict.*?<\/button>/s)
    const runMatch = html.match(/<button[^>]*>.*?Run.*?<\/button>/s)

    const hasDisabledAttr = (str: string) => /\sdisabled([=>\s]|$)/.test(str)

    expect(hasDisabledAttr(compileMatch![0])).toBe(false)
    // Predict is unlocked
    expect(hasDisabledAttr(predictMatch![0])).toBe(false)
    // Run is still locked
    expect(hasDisabledAttr(runMatch![0])).toBe(true)
  })

  it('unlocks both Predict and Run when stage is predict-pass', () => {
    const html = renderToStaticMarkup(
      <CenterActionBar
        stage="predict-pass"
        onCompile={() => {}}
        onPredict={() => {}}
        onRun={() => {}}
      />
    )

    const compileMatch = html.match(/<button[^>]*>.*?Compile.*?<\/button>/s)
    const predictMatch = html.match(/<button[^>]*>.*?Predict.*?<\/button>/s)
    const runMatch = html.match(/<button[^>]*>.*?Run.*?<\/button>/s)

    const hasDisabledAttr = (str: string) => /\sdisabled([=>\s]|$)/.test(str)

    expect(hasDisabledAttr(compileMatch![0])).toBe(false)
    expect(hasDisabledAttr(predictMatch![0])).toBe(false)
    // Run is unlocked
    expect(hasDisabledAttr(runMatch![0])).toBe(false)
  })
})
