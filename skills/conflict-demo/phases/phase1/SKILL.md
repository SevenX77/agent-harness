---
name: phase1
mode: logic
io:
  inputs:
    type: object
    properties:
      input_text:
        type: string
  outputs:
    type: object
    properties:
      summary:
        type: string
---

<python_callable>
def phase1(context):
    return {"summary": "hello"}
</python_callable>

# phase1
