"use client";

import { useState, useTransition } from "react";

import { API_BASE } from "@/lib/api";

export function SubscribeButton({
  targetType,
  targetValue,
  displayName,
}: {
  targetType: "topic" | "resource" | "source";
  targetValue: string;
  displayName: string;
}) {
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  function subscribe() {
    startTransition(async () => {
      setMessage("");
      try {
        const response = await fetch(`${API_BASE}/subscriptions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_type: targetType, target_value: targetValue, display_name: displayName }),
        });
        if (!response.ok) {
          throw new Error("订阅失败");
        }
        setMessage("已订阅");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "订阅失败");
      }
    });
  }

  return (
    <span className="meta">
      <button className="button" disabled={isPending} onClick={subscribe} type="button">
        {isPending ? "订阅中..." : "订阅"}
      </button>
      {message ? <span className="muted">{message}</span> : null}
    </span>
  );
}
