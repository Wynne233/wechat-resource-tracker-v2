"use client";

import Link from "next/link";
import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";

import {
  bulkDeleteAdminResources,
  bulkUpdateAdminResources,
  deleteAdminResource,
  type SearchResource,
} from "@/lib/api";

const STATUS_OPTIONS = [
  ["", "全部状态"],
  ["available", "可用"],
  ["review", "待复核"],
  ["suspected_update", "疑似更新"],
  ["suspected_down", "疑似失效"],
  ["down", "已失效"],
];

const RISK_OPTIONS = [
  ["", "全部风险"],
  ["low", "低风险"],
  ["medium", "中风险"],
  ["high", "高风险"],
];

function statusLabel(status: string) {
  return STATUS_OPTIONS.find(([value]) => value === status)?.[1] ?? status;
}

function riskLabel(risk: string) {
  return RISK_OPTIONS.find(([value]) => value === risk)?.[1] ?? risk;
}

export function ResourceWorkbench({ resources, total }: { resources: SearchResource[]; total: number }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [risk, setRisk] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [isPending, startTransition] = useTransition();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return resources.filter((resource) => {
      const matchesQuery =
        !q ||
        resource.canonical_name.toLowerCase().includes(q) ||
        resource.summary.toLowerCase().includes(q) ||
        resource.capability_tags.some((tag) => tag.toLowerCase().includes(q));
      const matchesStatus = !status || resource.current_status === status;
      const matchesRisk = !risk || resource.risk_level === risk;
      return matchesQuery && matchesStatus && matchesRisk;
    });
  }, [query, resources, risk, status]);

  const selectedCount = selected.length;

  function toggle(resourceId: string) {
    setSelected((current) => current.includes(resourceId) ? current.filter((id) => id !== resourceId) : [...current, resourceId]);
  }

  function toggleAll() {
    const ids = filtered.map((resource) => resource.id);
    setSelected((current) => current.length === ids.length ? [] : ids);
  }

  function run(action: () => Promise<{ message: string }>) {
    startTransition(async () => {
      setMessage("");
      try {
        const result = await action();
        setMessage(result.message);
        setSelected([]);
        router.refresh();
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "操作失败，请稍后重试。");
      }
    });
  }

  return (
    <section className="workbench">
      <div className="workbench-header">
        <div>
          <h2>资源工作台</h2>
          <p>当前载入 {resources.length} / {total} 个资源。优先处理待复核、高风险和疑似失效资源。</p>
        </div>
        <div className="workbench-stat">
          <strong>{selectedCount}</strong>
          <span>已选中</span>
        </div>
      </div>

      <div className="toolbar">
        <input className="input" onChange={(event) => setQuery(event.target.value)} placeholder="搜索资源名、摘要、标签" value={query} />
        <select className="select" onChange={(event) => setStatus(event.target.value)} value={status}>
          {STATUS_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <select className="select" onChange={(event) => setRisk(event.target.value)} value={risk}>
          {RISK_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </div>

      <div className="bulkbar">
        <button className="button ghost" disabled={!filtered.length} onClick={toggleAll} type="button">
          {selectedCount === filtered.length && filtered.length ? "取消全选" : "选择当前结果"}
        </button>
        <button
          className="button secondary"
          disabled={!selectedCount || isPending}
          onClick={() => run(() => bulkUpdateAdminResources({ resource_ids: selected, current_status: "available", note: "批量标记可用" }))}
          type="button"
        >
          标记可用
        </button>
        <button
          className="button warn"
          disabled={!selectedCount || isPending}
          onClick={() => run(() => bulkUpdateAdminResources({ resource_ids: selected, current_status: "review", note: "批量转入待复核" }))}
          type="button"
        >
          转入待复核
        </button>
        <button
          className="button danger"
          disabled={!selectedCount || isPending}
          onClick={() => {
            if (confirm(`确认删除 ${selectedCount} 个资源？相关评分、状态时间线和通知也会删除。`)) {
              run(() => bulkDeleteAdminResources(selected));
            }
          }}
          type="button"
        >
          批量删除
        </button>
        {message ? <span className="muted">{message}</span> : null}
      </div>

      <div className="resource-table-wrap">
        <table className="resource-table">
          <thead>
            <tr>
              <th>选择</th>
              <th>资源</th>
              <th>状态</th>
              <th>风险</th>
              <th>评分</th>
              <th>证据</th>
              <th>最近提及</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((resource) => (
              <tr key={resource.id}>
                <td>
                  <input checked={selected.includes(resource.id)} onChange={() => toggle(resource.id)} type="checkbox" />
                </td>
                <td className="resource-name-cell">
                  <Link className="resource-name" href={`/resources/${resource.id}`}>{resource.canonical_name}</Link>
                  <p>{resource.summary}</p>
                  <div className="tag-row">
                    {resource.capability_tags.slice(0, 4).map((tag) => <span className="tag" key={tag}>{tag}</span>)}
                  </div>
                </td>
                <td><span className={`status ${resource.current_status}`}>{statusLabel(resource.current_status)}</span></td>
                <td><span className={`risk ${resource.risk_level}`}>{riskLabel(resource.risk_level)}</span></td>
                <td><strong>{resource.latest_score.toFixed(1)}</strong><span className="muted"> / {resource.latest_grade}</span></td>
                <td>{resource.source_count} 个来源<br /><span className="muted">{resource.mention_count} 次提及</span></td>
                <td>{resource.last_mentioned_at ? new Date(resource.last_mentioned_at).toLocaleDateString("zh-CN") : "-"}</td>
                <td className="table-actions">
                  <Link className="button small ghost" href={`/resources/${resource.id}`}>详情</Link>
                  <button
                    className="button small danger"
                    disabled={isPending}
                    onClick={() => {
                      if (confirm(`确认删除 ${resource.canonical_name}？`)) {
                        run(() => deleteAdminResource(resource.id));
                      }
                    }}
                    type="button"
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
            {!filtered.length ? (
              <tr>
                <td colSpan={8}>
                  <div className="empty-state">没有符合条件的资源。换个关键词，或清除筛选条件。</div>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
