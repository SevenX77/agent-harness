---
name: phase2
mode: logic
io:
  inputs:
    type: object
    properties:
      summary:
        type: string
  outputs:
    type: object
    properties:
      summary:
        type: string
---

<python_callable>
def phase2(context):
    return {"summary": "world"}
</python_callable>

# phase2
