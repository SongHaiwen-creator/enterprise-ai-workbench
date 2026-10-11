"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, type GroundedCitation } from "@/utils/api";
import { getDocument } from "@/utils/knowledge-admin";

type Props = {
  workspaceId: string; knowledgeBaseId: string; accessToken: string;
  citation: GroundedCitation; onUnauthorized: () => void;
};

export function CitationVersion(props: Props) {
  return <VersionStatus key={`${props.workspaceId}:${props.knowledgeBaseId}:${props.accessToken}:${props.citation.document_id}`} {...props} />;
}

function VersionStatus({ workspaceId, knowledgeBaseId, accessToken, citation, onUnauthorized }: Props) {
  const [status, setStatus] = useState("当前状态未确认；引用保留回答时的文档版本。");
  const [busy, setBusy] = useState(false);
  const live = useRef(false), pending = useRef(false);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  async function inspect() {
    if (pending.current) return;
    pending.current = true; setBusy(true);
    try {
      const metadata = await getDocument(workspaceId, knowledgeBaseId, citation.document_id, accessToken);
      if (!live.current) return;
      setStatus(metadata.status === "disabled" ? "已禁用版本；此摘录仍指向回答时的内容。"
        : metadata.is_current ? "当前版本；此摘录来自回答时的检索。" : "历史版本；新的检索使用当前有效版本。");
    } catch (reason) {
      if (!live.current) return;
      if (reason instanceof ApiError && reason.status === 401) onUnauthorized();
      setStatus("当前状态未确认，版本元数据暂不可读取。已有摘录未被替换。");
    } finally {
      pending.current = false;
      if (live.current) setBusy(false);
    }
  }
  return <div className="citation-version"><p aria-live="polite">{status}</p>
    <button disabled={busy || !knowledgeBaseId} onClick={() => void inspect()}>{busy ? "正在读取版本状态…" : "查看版本状态"}</button>
  </div>;
}
