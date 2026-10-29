import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { AsyncBlock, ErrorMessage } from "../components/common";
import { formatDate } from "../format";
import { useAsync } from "../hooks";

export function ProjectsPage() {
  const projects = useAsync(() => api.listProjects({ limit: 100 }), []);
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<unknown>();
  const [saving, setSaving] = useState(false);

  const create = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setError(undefined);
    try {
      const project = await api.createProject({ name, description: description || undefined });
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError(err);
      setSaving(false);
    }
  };

  return (
    <>
      <h1>Projects</h1>
      <p className="subtitle">Each project groups datasets, model configurations, runs and baselines.</p>
      <AsyncBlock state={projects}>
        {(page) =>
          page.items.length === 0 ? (
            <div className="alert info">
              No projects yet. Create one below, or run <code>llm-eval</code> against the API.
            </div>
          ) : (
            <div className="grid">
              {page.items.map((project) => (
                <Link
                  key={project.id}
                  to={`/projects/${project.id}`}
                  className="card"
                  style={{ textDecoration: "none", color: "inherit" }}
                >
                  <h3>{project.name}</h3>
                  {project.description && <p className="muted">{project.description}</p>}
                  <div className="muted">Updated {formatDate(project.updated_at)}</div>
                </Link>
              ))}
            </div>
          )
        }
      </AsyncBlock>

      <h2>New project</h2>
      <form className="form card" onSubmit={create}>
        <label>
          Name
          <input required maxLength={200} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Description (optional)
          <textarea
            maxLength={2000}
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <ErrorMessage error={error} />
        <div>
          <button className="primary" type="submit" disabled={saving || !name.trim()}>
            {saving ? "Creating…" : "Create project"}
          </button>
        </div>
      </form>
    </>
  );
}
