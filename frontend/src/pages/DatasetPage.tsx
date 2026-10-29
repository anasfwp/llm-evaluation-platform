import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, downloadUrl } from "../api/client";
import { AsyncBlock, Pager } from "../components/common";
import { formatDate } from "../format";
import { useAsync } from "../hooks";

const PAGE = 25;

export function DatasetPage() {
  const { datasetId = "" } = useParams();
  const dataset = useAsync(() => api.getDataset(datasetId), [datasetId]);
  const versions = useAsync(() => api.listVersions(datasetId), [datasetId]);
  const [version, setVersion] = useState<number | null>(null);
  const [tag, setTag] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const selected = version ?? dataset.data?.current_version ?? null;
  const cases = useAsync(
    () =>
      selected === null
        ? Promise.resolve(undefined)
        : api.getVersion(datasetId, selected, { tag, q: search, limit: PAGE, offset }),
    [datasetId, selected, tag, search, offset],
  );

  return (
    <>
      <AsyncBlock state={dataset}>
        {(d) => (
          <>
            <div className="breadcrumbs">
              <Link to="/">Projects</Link> /{" "}
              <Link to={`/projects/${d.project_id}?tab=datasets`}>Project</Link> /
            </div>
            <h1>{d.name}</h1>
            {d.description && <p className="subtitle">{d.description}</p>}
            <div className="toolbar">
              <a className="button" href={downloadUrl(`/datasets/${d.id}/export`, { version: selected, format: "json" })}>
                Export JSON
              </a>
              <a
                className="button"
                href={downloadUrl(`/datasets/${d.id}/export`, { version: selected, format: "jsonl" })}
              >
                Export JSONL
              </a>
            </div>
          </>
        )}
      </AsyncBlock>

      <h2>Versions</h2>
      <AsyncBlock state={versions}>
        {(items) => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Version</th>
                  <th className="num">Cases</th>
                  <th>Content hash</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((v) => (
                  <tr key={v.id} aria-current={v.version_number === selected ? "true" : undefined}>
                    <td>
                      v{v.version_number}
                      {v.version_number === selected && <strong> (viewing)</strong>}
                    </td>
                    <td className="num">{v.case_count}</td>
                    <td className="mono" title={v.content_hash}>
                      {v.content_hash.slice(0, 19)}…
                    </td>
                    <td>{formatDate(v.created_at)}</td>
                    <td>
                      {v.version_number !== selected && (
                        <button
                          onClick={() => {
                            setVersion(v.version_number);
                            setOffset(0);
                          }}
                        >
                          View
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncBlock>

      <h2>Cases</h2>
      <div className="toolbar">
        <label>
          Search case keys
          <input
            type="search"
            value={search}
            maxLength={200}
            onChange={(e) => {
              setSearch(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          Tag
          <input
            value={tag}
            maxLength={100}
            onChange={(e) => {
              setTag(e.target.value);
              setOffset(0);
            }}
          />
        </label>
      </div>
      <AsyncBlock state={cases}>
        {(detail) =>
          detail && (
            <>
              <p className="muted">
                {detail.matching_cases} of {detail.case_count} cases match.
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Case</th>
                      <th>Input</th>
                      <th>Expected output</th>
                      <th>Tags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.cases.map((c) => (
                      <tr key={c.case_key}>
                        <td className="mono">{c.case_key}</td>
                        <td>
                          <pre className="output">{JSON.stringify(c.input, null, 2)}</pre>
                        </td>
                        <td>
                          {c.expected_output ?? <span className="muted">open-ended</span>}
                          {c.retrieved_contexts.length > 0 && (
                            <div className="muted">{c.retrieved_contexts.length} retrieved contexts</div>
                          )}
                        </td>
                        <td>
                          {c.tags.map((t) => (
                            <button
                              key={t}
                              type="button"
                              style={{ marginRight: 4, minHeight: 0, padding: "0 6px" }}
                              onClick={() => {
                                setTag(t);
                                setOffset(0);
                              }}
                              aria-label={`Filter by tag ${t}`}
                            >
                              {t}
                            </button>
                          ))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pager total={detail.matching_cases} limit={PAGE} offset={offset} onChange={setOffset} />
            </>
          )
        }
      </AsyncBlock>
    </>
  );
}
