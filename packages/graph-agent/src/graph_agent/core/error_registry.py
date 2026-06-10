"""Static metadata for V0.3.0 framework error codes."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, NamedTuple

ERROR_CATALOG_VERSION = "engine-mvp1.error-catalog.v1"
ERROR_METADATA_SCHEMA_VERSION = "engine-mvp1.error-metadata.v1"
_PUBLIC_DOC_BASE_URL = "https://docs.graph-agent.dev/errors"
_DEFAULT_DETAILS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
}


class ErrorCodeMetadata(NamedTuple):
    code: str
    level: str
    stage: tuple[str, ...]
    doc_link: str
    remediation: str = ""
    doc_ref: str = ""
    doc_url: str = ""
    details_schema: dict[str, Any] = _DEFAULT_DETAILS_SCHEMA
    schema_version: str = ERROR_METADATA_SCHEMA_VERSION
    status: str = "active"


ERROR_REGISTRY: dict[str, ErrorCodeMetadata] = {
    '[F-v3-graph-schema-unknown-field]': ErrorCodeMetadata('[F-v3-graph-schema-unknown-field]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-name-invalid]': ErrorCodeMetadata('[F-v3-graph-name-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-schema-version-mismatch]': ErrorCodeMetadata('[F-v3-graph-schema-version-mismatch]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-llm-role-unknown]': ErrorCodeMetadata('[F-v3-graph-llm-role-unknown]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-root-missing]': ErrorCodeMetadata('[F-v3-graph-root-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md#21-skill-源码树'),
    '[F-v3-graph-phases-dir-missing]': ErrorCodeMetadata('[F-v3-graph-phases-dir-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md#21-skill-源码树'),
    '[F-v3-graph-phases-missing]': ErrorCodeMetadata('[F-v3-graph-phases-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-phase-id-invalid]': ErrorCodeMetadata('[F-v3-graph-phase-id-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-phase-name-mismatch]': ErrorCodeMetadata('[F-v3-graph-phase-name-mismatch]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-phase-id-duplicate]': ErrorCodeMetadata('[F-v3-graph-phase-id-duplicate]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-depends-unknown]': ErrorCodeMetadata('[F-v3-graph-depends-unknown]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-output-phase-invalid]': ErrorCodeMetadata('[F-v3-graph-output-phase-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-phase-cycle]': ErrorCodeMetadata('[F-v3-graph-phase-cycle]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-phase-island]': ErrorCodeMetadata('[F-v3-graph-phase-island]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-phase-dir-missing]': ErrorCodeMetadata('[F-v3-graph-phase-dir-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md#21-skill-源码树'),
    '[F-v3-graph-phase-mode-ambiguous]': ErrorCodeMetadata('[F-v3-graph-phase-mode-ambiguous]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md#21-skill-源码树'),
    '[F-v3-graph-phase-node-missing]': ErrorCodeMetadata('[F-v3-graph-phase-node-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md#21-skill-源码树'),
    '[F-v3-graph-io-not-object]': ErrorCodeMetadata('[F-v3-graph-io-not-object]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-io-schema-invalid]': ErrorCodeMetadata('[F-v3-graph-io-schema-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-graph-io-physical-file-deprecated]': ErrorCodeMetadata('[F-v3-graph-io-physical-file-deprecated]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/01-physical-layout/mvp1-alignment.md#21-skill-源码树'),
    '[F-v3-graph-dataflow-source-missing]': ErrorCodeMetadata('[F-v3-graph-dataflow-source-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-compile-recursion-cycle]': ErrorCodeMetadata('[F-v3-compile-recursion-cycle]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md#compile-domain'),
    '[F-v3-compile-depth-exceeded]': ErrorCodeMetadata('[F-v3-compile-depth-exceeded]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md#compile-domain'),
    '[F-v3-logic-schema-unknown-field]': ErrorCodeMetadata('[F-v3-logic-schema-unknown-field]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-name-invalid]': ErrorCodeMetadata('[F-v3-logic-name-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-io-schema-invalid]': ErrorCodeMetadata('[F-v3-logic-io-schema-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-actions-empty]': ErrorCodeMetadata('[F-v3-logic-actions-empty]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-action-name-invalid]': ErrorCodeMetadata('[F-v3-logic-action-name-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-action-dir-missing]': ErrorCodeMetadata('[F-v3-logic-action-dir-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-action-not-found]': ErrorCodeMetadata('[F-v3-logic-action-not-found]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-action-entrypoint-missing]': ErrorCodeMetadata('[F-v3-logic-action-entrypoint-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-action-purity-violation]': ErrorCodeMetadata('[F-v3-logic-action-purity-violation]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-action-return-invalid]': ErrorCodeMetadata('[F-v3-logic-action-return-invalid]', 'FATAL', ('运行期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-output-field-undeclared]': ErrorCodeMetadata('[F-v3-logic-output-field-undeclared]', 'FATAL', ('运行期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-validator-type-invalid]': ErrorCodeMetadata('[F-v3-logic-validator-type-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-validator-missing]': ErrorCodeMetadata('[F-v3-logic-validator-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-validator-entrypoint-missing]': ErrorCodeMetadata('[F-v3-logic-validator-entrypoint-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-logic-validator-failed]': ErrorCodeMetadata('[F-v3-logic-validator-failed]', 'FATAL', ('运行期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-iterate-accumulate-fields-missing]': ErrorCodeMetadata('[F-v3-iterate-accumulate-fields-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md#6-mvp1-新增码目标未计入现有-93-码'),
    '[F-v3-iterate-over-not-list]': ErrorCodeMetadata('[F-v3-iterate-over-not-list]', 'FATAL', ('编译期', '运行期'), 'docs/engine/mvp1/01-contract/03-compile-rules/mvp1-alignment.md#6-mvp1-新增码目标未计入现有-93-码'),
    '[F-v3-agent-validator-failed]': ErrorCodeMetadata('[F-v3-agent-validator-failed]', 'FATAL', ('运行期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-subgraph-validator-failed]': ErrorCodeMetadata('[F-v3-subgraph-validator-failed]', 'FATAL', ('运行期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-subgraph-schema-unknown-field]': ErrorCodeMetadata('[F-v3-subgraph-schema-unknown-field]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-subgraph-name-invalid]': ErrorCodeMetadata('[F-v3-subgraph-name-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-subgraph-target-skill-invalid]': ErrorCodeMetadata('[F-v3-subgraph-target-skill-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#21-子图-path-引用契约mvp1-权威'),
    '[F-v3-subgraph-io-schema-invalid]': ErrorCodeMetadata('[F-v3-subgraph-io-schema-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#21-子图-path-引用契约mvp1-权威'),
    '[F-v3-subgraph-io-mismatch]': ErrorCodeMetadata('[F-v3-subgraph-io-mismatch]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#21-子图-path-引用契约mvp1-权威'),
    '[F-v3-subgraph-io-schema-incompatible]': ErrorCodeMetadata('[F-v3-subgraph-io-schema-incompatible]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#21-子图-path-引用契约mvp1-权威'),
    '[F-v3-agent-schema-unknown-field]': ErrorCodeMetadata('[F-v3-agent-schema-unknown-field]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-name-invalid]': ErrorCodeMetadata('[F-v3-agent-name-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-llm-role-unknown]': ErrorCodeMetadata('[F-v3-agent-llm-role-unknown]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-io-schema-invalid]': ErrorCodeMetadata('[F-v3-agent-io-schema-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-output-schema-invalid]': ErrorCodeMetadata('[F-v3-agent-output-schema-invalid]', 'FATAL', ('运行期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-output-schema-missing]': ErrorCodeMetadata('[F-v3-agent-output-schema-missing]', 'FATAL', ('运行期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-tool-unknown]': ErrorCodeMetadata('[F-v3-agent-tool-unknown]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-subagent-invalid]': ErrorCodeMetadata('[F-v3-agent-subagent-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-subgraph-invalid]': ErrorCodeMetadata('[F-v3-agent-subgraph-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-max-iterations-invalid]': ErrorCodeMetadata('[F-v3-agent-max-iterations-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-body-tag-unknown]': ErrorCodeMetadata('[F-v3-agent-body-tag-unknown]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-role-missing]': ErrorCodeMetadata('[F-v3-agent-role-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-goal-missing]': ErrorCodeMetadata('[F-v3-agent-goal-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-step-invalid]': ErrorCodeMetadata('[F-v3-agent-step-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-protocol-invalid]': ErrorCodeMetadata('[F-v3-agent-protocol-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-example-invalid]': ErrorCodeMetadata('[F-v3-agent-example-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-mention-type-unknown]': ErrorCodeMetadata('[F-v3-mention-type-unknown]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-mention-syntax-invalid]': ErrorCodeMetadata('[F-v3-mention-syntax-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-mention-target-not-found]': ErrorCodeMetadata('[F-v3-mention-target-not-found]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-mention-unused-registry-entry]': ErrorCodeMetadata('[F-v3-mention-unused-registry-entry]', 'WARN', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-reference-invalid]': ErrorCodeMetadata('[F-v3-resource-reference-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-reference-id-invalid]': ErrorCodeMetadata('[F-v3-resource-reference-id-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-reference-path-invalid]': ErrorCodeMetadata('[F-v3-resource-reference-path-invalid]', 'FATAL', ('编译期', '运行期'), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-reference-summary-missing]': ErrorCodeMetadata('[F-v3-resource-reference-summary-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-reference-not-found]': ErrorCodeMetadata('[F-v3-resource-reference-not-found]', 'FATAL', ('运行期',), 'docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/mvp1-alignment.md#3-接口契约'),
    '[F-v3-resource-example-invalid]': ErrorCodeMetadata('[F-v3-resource-example-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-example-id-invalid]': ErrorCodeMetadata('[F-v3-resource-example-id-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-example-path-missing]': ErrorCodeMetadata('[F-v3-resource-example-path-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-example-path-invalid]': ErrorCodeMetadata('[F-v3-resource-example-path-invalid]', 'FATAL', ('编译期', '运行期'), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-example-summary-missing]': ErrorCodeMetadata('[F-v3-resource-example-summary-missing]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-resource-example-not-found]': ErrorCodeMetadata('[F-v3-resource-example-not-found]', 'FATAL', ('运行期',), 'docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/mvp1-alignment.md#3-接口契约'),
    '[F-v3-reference-reader-failed]': ErrorCodeMetadata('[F-v3-reference-reader-failed]', 'WARN', ('装配期',), 'docs/engine/mvp1/02-mechanism/03-assemble/mvp1-alignment.md#2-数据流--机制'),
    '[F-v3-resolver-skill-id-invalid]': ErrorCodeMetadata('[F-v3-resolver-skill-id-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md#3-接口契约'),
    '[F-v3-skill-id-ambiguous]': ErrorCodeMetadata('[F-v3-skill-id-ambiguous]', 'FATAL', ('编译期', '装配期'), 'docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md#3-接口契约'),
    '[F-v3-skill-not-registered]': ErrorCodeMetadata('[F-v3-skill-not-registered]', 'FATAL', ('编译期', '装配期'), 'docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md#3-接口契约'),
    '[F-v3-resolver-path-invalid]': ErrorCodeMetadata('[F-v3-resolver-path-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md#3-接口契约'),
    '[F-v3-resolver-interface-invalid]': ErrorCodeMetadata('[F-v3-resolver-interface-invalid]', 'FATAL', ('编译期',), 'docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md#3-接口契约'),
    '[F-v3-resolver-missing]': ErrorCodeMetadata('[F-v3-resolver-missing]', 'FATAL', ('运行期',), 'docs/engine/mvp1/02-mechanism/02-resolver/mvp1-alignment.md#3-接口契约'),
    '[F-v3-cognitive-slot-render-failed]': ErrorCodeMetadata('[F-v3-cognitive-slot-render-failed]', 'FATAL', ('装配期',), 'docs/engine/mvp1/02-mechanism/03-assemble/mvp1-alignment.md#2-数据流--机制'),
    '[F-v3-cognitive-output-schema-render-failed]': ErrorCodeMetadata('[F-v3-cognitive-output-schema-render-failed]', 'FATAL', ('装配期',), 'docs/engine/mvp1/02-mechanism/03-assemble/mvp1-alignment.md#2-数据流--机制'),
    '[F-v3-cognitive-output-schema-invalid]': ErrorCodeMetadata('[F-v3-cognitive-output-schema-invalid]', 'FATAL', ('装配期', '装配前'), 'docs/engine/mvp1/02-mechanism/03-assemble/mvp1-alignment.md#2-数据流--机制'),
    '[F-v3-reference-reader-input-invalid]': ErrorCodeMetadata('[F-v3-reference-reader-input-invalid]', 'FATAL', ('装配期',), 'docs/engine/mvp1/02-mechanism/03-assemble/mvp1-alignment.md#2-数据流--机制'),
    '[F-v3-reference-reader-output-invalid]': ErrorCodeMetadata('[F-v3-reference-reader-output-invalid]', 'FATAL', ('装配期',), 'docs/engine/mvp1/02-mechanism/03-assemble/mvp1-alignment.md#2-数据流--机制'),
    '[F-v3-tool-argument-invalid]': ErrorCodeMetadata('[F-v3-tool-argument-invalid]', 'FATAL', ('运行期',), 'docs/engine/mvp1/02-mechanism/05-run-inner/04-tools/mvp1-alignment.md#3-接口契约'),
    '[F-v3-runtime-state-mapping-failed]': ErrorCodeMetadata('[F-v3-runtime-state-mapping-failed]', 'FATAL', ('运行期',), 'docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md#3-接口契约'),
    '[F-v3-runtime-phase-failed]': ErrorCodeMetadata('[F-v3-runtime-phase-failed]', 'FATAL', ('运行期',), 'docs/engine/mvp1/02-mechanism/04-run-outer/01-graph-exec/mvp1-alignment.md#3-接口契约'),
    '[F-v3-sequential-overwrite-unauthorized]': ErrorCodeMetadata('[F-v3-sequential-overwrite-unauthorized]', 'FATAL', ('编译期',), 'docs/engine/mvp1/01-contract/02-skill-syntax/mvp1-alignment.md#2-语法部件清单--mvp1-写入状态'),
    '[F-v3-agent-exit-control-failed]': ErrorCodeMetadata('[F-v3-agent-exit-control-failed]', 'FATAL', ('运行期',), 'docs/engine/mvp1/02-mechanism/05-run-inner/05-exit-control/mvp1-alignment.md'),
}


_CATALOG_METADATA_BY_CODE: dict[str, tuple[str, str]] = {
    '[F-v3-graph-schema-unknown-field]': ('graph', '删除字段或纳入 spec'),
    '[F-v3-graph-name-invalid]': ('graph', '改为小写开头标识'),
    '[F-v3-graph-schema-version-mismatch]': ('graph', '升级/降级 spec 或 engine'),
    '[F-v3-graph-llm-role-unknown]': ('graph', '使用 `llm_roles.yaml` 中角色'),
    '[F-v3-graph-root-missing]': ('graph', '创建精确命名的 `GRAPH.md`'),
    '[F-v3-graph-phases-dir-missing]': ('graph', '创建 phases 目录'),
    '[F-v3-graph-phases-missing]': ('graph', '添加 `phases: [...]` 名字注册'),
    '[F-v3-graph-phase-id-invalid]': ('graph', '修正 phase name 为合法标识'),
    '[F-v3-graph-phase-name-mismatch]': ('graph', '对齐 body、frontmatter 和目录名'),
    '[F-v3-graph-phase-id-duplicate]': ('graph', '去重'),
    '[F-v3-graph-depends-unknown]': ('graph', '修正依赖名'),
    '[F-v3-graph-output-phase-invalid]': ('graph', '修正 `<phase ... output>` 标记'),
    '[F-v3-graph-phase-cycle]': ('graph', '打断循环依赖'),
    '[F-v3-graph-phase-island]': ('graph', '增加依赖连接或删除孤岛'),
    '[F-v3-graph-phase-dir-missing]': ('graph', '创建 `phases/<id>/`'),
    '[F-v3-graph-phase-mode-ambiguous]': ('graph', '保留 `LOGIC.md`/`SUBGRAPH.md`/`SKILL.md` 之一'),
    '[F-v3-graph-phase-node-missing]': ('graph', '添加 `LOGIC.md`/`SUBGRAPH.md`/`SKILL.md` 之一'),
    '[F-v3-graph-io-not-object]': ('graph', '设置 `type: object`'),
    '[F-v3-graph-io-schema-invalid]': ('graph', '修正 schema'),
    '[F-v3-graph-io-physical-file-deprecated]': ('graph', '改为 inline `io.inputs` / `io.outputs`'),
    '[F-v3-graph-dataflow-source-missing]': ('graph', '补依赖或调整 IO'),
    '[F-v3-sequential-overwrite-unauthorized]': ('graph', '在 Frontmatter 中声明 allow_sequential_overwrite 允许覆盖'),
    '[F-v3-compile-recursion-cycle]': ('compile', '打断 skill 间循环引用或抽出共享子图'),
    '[F-v3-compile-depth-exceeded]': ('compile', '降低嵌套深度或合并中间 skill'),
    '[F-v3-iterate-accumulate-fields-missing]': ('compile', '在 loop 节点 `io.inputs` 声明 item 与累积字段'),
    '[F-v3-iterate-over-not-list]': ('compile', '调整 `over` 字段 schema、输入值或 iterate 声明'),
    '[F-v3-logic-schema-unknown-field]': ('logic', '删除字段'),
    '[F-v3-logic-name-invalid]': ('logic', '修正命名'),
    '[F-v3-logic-io-schema-invalid]': ('logic', '修正 object schema'),
    '[F-v3-logic-actions-empty]': ('logic', '声明至少一个 action'),
    '[F-v3-logic-action-name-invalid]': ('logic', '使用一级合法函数名'),
    '[F-v3-logic-action-dir-missing]': ('logic', '创建目录或注册通用 action'),
    '[F-v3-logic-action-not-found]': ('logic', '增加 `<name>.py` 或注册通用 action'),
    '[F-v3-logic-action-entrypoint-missing]': ('logic', '导出 `run`'),
    '[F-v3-logic-action-purity-violation]': ('logic', "移除 `open('w')` 等非纯操作"),
    '[F-v3-logic-action-return-invalid]': ('logic', '返回 dict'),
    '[F-v3-logic-output-field-undeclared]': ('logic', '更新 `io.outputs` 或删字段'),
    '[F-v3-logic-validator-type-invalid]': ('logic', '改为 true/false'),
    '[F-v3-logic-validator-missing]': ('logic', '增加同级 `validator.py`'),
    '[F-v3-logic-validator-entrypoint-missing]': ('logic', '导出 `validate`'),
    '[F-v3-logic-validator-failed]': ('logic', '修正输出或校验规则'),
    '[F-v3-agent-validator-failed]': ('logic', '触发 LLM 重试反馈'),
    '[F-v3-subgraph-validator-failed]': ('logic', '检查子图业务规则'),
    '[F-v3-subgraph-schema-unknown-field]': ('subgraph', '删除字段'),
    '[F-v3-subgraph-name-invalid]': ('subgraph', '修正命名'),
    '[F-v3-subgraph-target-skill-invalid]': ('subgraph', '使用 registry skill id'),
    '[F-v3-subgraph-io-schema-invalid]': ('subgraph', '修正 object schema'),
    '[F-v3-subgraph-io-mismatch]': ('subgraph', '对齐父 phase 和子 GRAPH IO'),
    '[F-v3-subgraph-io-schema-incompatible]': ('subgraph', '对齐字段 schema'),
    '[F-v3-agent-schema-unknown-field]': ('agent', '删除字段'),
    '[F-v3-agent-name-invalid]': ('agent', '修正命名'),
    '[F-v3-agent-llm-role-unknown]': ('agent', '使用已注册角色'),
    '[F-v3-agent-io-schema-invalid]': ('agent', '修正 schema'),
    '[F-v3-agent-output-schema-invalid]': ('agent', '触发 LLM 重试反馈'),
    '[F-v3-agent-output-schema-missing]': ('agent', '修正 AST / pipeline'),
    '[F-v3-agent-exit-control-failed]': ('agent', '让模型调用 finish_task 并提交通过 schema 的业务输出'),
    '[F-v3-agent-tool-unknown]': ('agent', '注册 tool 或删引用'),
    '[F-v3-agent-subagent-invalid]': ('agent', '补 name/target_skill/description'),
    '[F-v3-agent-subgraph-invalid]': ('agent', '补 name/target_skill/description'),
    '[F-v3-agent-max-iterations-invalid]': ('agent', '设为 1..50'),
    '[F-v3-agent-body-tag-unknown]': ('agent', '仅保留 5 类白名单标签'),
    '[F-v3-agent-role-missing]': ('agent', '添加 role'),
    '[F-v3-agent-goal-missing]': ('agent', '添加 goal'),
    '[F-v3-agent-step-invalid]': ('agent', '修正 step'),
    '[F-v3-agent-protocol-invalid]': ('agent', '修正 protocol'),
    '[F-v3-agent-example-invalid]': ('agent', '修正 `<example id>`'),
    '[F-v3-mention-type-unknown]': ('mention', '改用合法 type'),
    '[F-v3-mention-syntax-invalid]': ('mention', '改成 `@type:NAME`'),
    '[F-v3-mention-target-not-found]': ('mention', '注册目标或修正文案'),
    '[F-v3-mention-unused-registry-entry]': ('mention', '确认是否保留'),
    '[F-v3-resource-reference-invalid]': ('resource', '补 id/path/summary'),
    '[F-v3-resource-reference-id-invalid]': ('resource', '修正 id'),
    '[F-v3-resource-reference-path-invalid]': ('resource', '修正路径'),
    '[F-v3-resource-reference-summary-missing]': ('resource', '补 summary'),
    '[F-v3-resource-reference-not-found]': ('resource', '使用 registry 中 id'),
    '[F-v3-resource-example-invalid]': ('resource', '补 id/path/summary'),
    '[F-v3-resource-example-id-invalid]': ('resource', '修正 id'),
    '[F-v3-resource-example-path-missing]': ('resource', '补 path'),
    '[F-v3-resource-example-path-invalid]': ('resource', '修正路径'),
    '[F-v3-resource-example-summary-missing]': ('resource', '补 summary'),
    '[F-v3-resource-example-not-found]': ('resource', '使用 registry 中 id'),
    '[F-v3-reference-reader-failed]': ('resource', '查看 trace; 可依赖降级内容继续跑'),
    '[F-v3-resolver-skill-id-invalid]': ('resolver', '修正 target_skill'),
    '[F-v3-skill-id-ambiguous]': ('resolver', '收窄 search paths 或移除重复注册'),
    '[F-v3-skill-not-registered]': ('resolver', '在 Studio 导入或注册 skill'),
    '[F-v3-resolver-path-invalid]': ('resolver', '修正 registry 记录'),
    '[F-v3-resolver-interface-invalid]': ('resolver', '实现单方法 `resolve_skill`'),
    '[F-v3-resolver-missing]': ('resolver', '调用入口传入 resolver'),
    '[F-v3-cognitive-slot-render-failed]': ('cognitive / tool / runtime', '检查 body AST'),
    '[F-v3-cognitive-output-schema-render-failed]': ('cognitive / tool / runtime', '修正 `io.outputs`'),
    '[F-v3-cognitive-output-schema-invalid]': ('cognitive / tool / runtime', '检查 Agent 的 `io.outputs` 或装配传入 schema'),
    '[F-v3-reference-reader-input-invalid]': ('cognitive / tool / runtime', '检查 references registry'),
    '[F-v3-reference-reader-output-invalid]': ('cognitive / tool / runtime', '修 reader 模块'),
    '[F-v3-tool-argument-invalid]': ('cognitive / tool / runtime', '修正 tool 调用参数'),
    '[F-v3-runtime-state-mapping-failed]': ('cognitive / tool / runtime', '检查 phase IO 和上游输出'),
    '[F-v3-runtime-phase-failed]': ('cognitive / tool / runtime', '查看 trace 原始异常'),
}


def _code_slug(code: str) -> str:
    return code.strip("[]")


def _metadata_doc_ref(code: str) -> str:
    return f"graph-agent://errors/{_code_slug(code)}"


def _metadata_doc_url(code: str) -> str:
    return f"{_PUBLIC_DOC_BASE_URL}/{_code_slug(code)}"


def _with_catalog_metadata(metadata: ErrorCodeMetadata) -> ErrorCodeMetadata:
    domain_and_remediation = _CATALOG_METADATA_BY_CODE.get(metadata.code)
    if domain_and_remediation is None:
        raise RuntimeError(f"missing P0-2 catalog metadata for {metadata.code}")
    _domain, remediation = domain_and_remediation
    return metadata._replace(
        remediation=remediation,
        doc_ref=_metadata_doc_ref(metadata.code),
        doc_url=_metadata_doc_url(metadata.code),
        details_schema=deepcopy(_DEFAULT_DETAILS_SCHEMA),
        schema_version=ERROR_METADATA_SCHEMA_VERSION,
        status="active",
    )


def _assert_catalog_metadata_matches_registry(registry: dict[str, ErrorCodeMetadata]) -> None:
    registry_codes = set(registry)
    metadata_codes = set(_CATALOG_METADATA_BY_CODE)
    missing = sorted(registry_codes - metadata_codes)
    extra = sorted(metadata_codes - registry_codes)
    if missing or extra:
        raise RuntimeError(
            "P0-2 catalog metadata must match ERROR_REGISTRY keys exactly: "
            f"missing={missing}, extra={extra}"
        )


def _catalog_item(metadata: ErrorCodeMetadata) -> dict[str, Any]:
    domain, _remediation = _CATALOG_METADATA_BY_CODE[metadata.code]
    return {
        "code": metadata.code,
        "level": metadata.level,
        "stage": list(metadata.stage),
        "domain": domain,
        "remediation": metadata.remediation,
        "doc_link": metadata.doc_link,
        "doc_ref": metadata.doc_ref,
        "doc_url": metadata.doc_url,
        "status": metadata.status,
        "details_schema": deepcopy(metadata.details_schema),
        "schema_version": metadata.schema_version,
    }


def export_error_metadata(code: str) -> dict[str, Any]:
    metadata = ERROR_REGISTRY.get(code)
    if metadata is None:
        raise ValueError(f"unknown graph_agent error code: {code}")
    return _catalog_item(metadata)


def export_error_catalog() -> dict[str, Any]:
    return {
        "registry_version": ERROR_CATALOG_VERSION,
        "schema_version": ERROR_METADATA_SCHEMA_VERSION,
        "items": [export_error_metadata(code) for code in sorted(ERROR_REGISTRY)],
    }


_assert_catalog_metadata_matches_registry(ERROR_REGISTRY)
ERROR_REGISTRY = {code: _with_catalog_metadata(metadata) for code, metadata in ERROR_REGISTRY.items()}


__all__ = [
    "ERROR_CATALOG_VERSION",
    "ERROR_METADATA_SCHEMA_VERSION",
    "ERROR_REGISTRY",
    "ErrorCodeMetadata",
    "export_error_catalog",
    "export_error_metadata",
]
