"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import { checkSourceNow, updateSourceTracking } from "@/lib/api";

export function SourceActions({ sourceId, trackingStatus }: { sourceId: string; trackingStatus: string }) {
  const router = useRouter();
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();
  const active = trackingStatus === "active";

  function toggleTracking() {
    startTransition(async () => {
      setMessage("");
      try {
        await updateSourceTracking(sourceId, active ? "paused" : "active");
        setMessage(active ? "已暂停追踪" : "已恢复追踪");
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "操作失败");
      }
    });
  }

  function checkNow() {
    startTransition(async () => {
      setMessage("");
      try {
        const data = await checkSourceNow(sourceId);
        setMessage(data.message);
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "检查失败");
      }
    });
  }

  return (
    <div className="source-actions">
      <button className="button secondary small" disabled={isPending} onClick={toggleTracking} type="button">
        {active ? "暂停" : "追踪"}
      </button>
      <button className="button small" disabled={isPending || !active} onClick={checkNow} type="button">
        立即检查
      </button>
      {message ? <span className="muted">{message}</span> : null}
    </div>
  );
}
