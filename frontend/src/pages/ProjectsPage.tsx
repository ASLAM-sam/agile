import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { projectApi } from '@/api/resources';
import { PageHeader } from '@/components/layout/PageHeader';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { useAsync } from '@/hooks/useAsync';
import { relativeTime, truncate } from '@/lib/utils';
import type { Paged, Project } from '@/types';

const PAGE_SIZE = 12;

export function ProjectsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);

  const state = useAsync<Paged<Project>>(
    (signal) =>
      projectApi.list({ search: query, limit: PAGE_SIZE, offset: page * PAGE_SIZE }, signal),
    [query, page],
  );

  function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    setPage(0);
    setQuery(search.trim());
  }

  const total = state.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Projects"
        description={total > 0 ? `${total} project${total === 1 ? '' : 's'}` : undefined}
        actions={<Button onClick={() => navigate('/projects/new')}>New project</Button>}
      />

      <form onSubmit={handleSearch} className="mb-5 flex gap-2" role="search">
        <div className="relative flex-1">
          <svg
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-content-subtle"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.8}
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search projects…"
            aria-label="Search projects"
            className="w-full rounded-lg border border-edge bg-surface py-2 pl-9 pr-3 text-sm text-content placeholder:text-content-subtle hover:border-content-subtle focus:border-brand-500"
          />
        </div>
        <Button type="submit" variant="secondary">
          Search
        </Button>
      </form>

      {state.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index} className="skeleton h-40" aria-hidden="true" />
          ))}
        </div>
      ) : state.error ? (
        <Card>
          <ErrorState error={state.error} onRetry={state.reload} />
        </Card>
      ) : !state.data?.items.length ? (
        <Card>
          <EmptyState
            title={query ? 'No matching projects' : 'No projects yet'}
            description={
              query
                ? 'Try a different search term.'
                : 'Describe a software idea in plain language and the AI engineering team will build it.'
            }
            action={
              query ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setSearch('');
                    setQuery('');
                  }}
                >
                  Clear search
                </Button>
              ) : (
                <Button size="sm" onClick={() => navigate('/projects/new')}>
                  Create your first project
                </Button>
              )
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {state.data.items.map((project) => (
              <Link key={project.id} to={`/projects/${project.id}`} className="rounded-xl">
                <Card interactive className="flex h-full flex-col p-5">
                  <h2 className="line-clamp-2 text-sm font-semibold text-content">
                    {project.name}
                  </h2>
                  <p className="mt-2 flex-1 text-xs leading-relaxed text-content-muted">
                    {truncate(project.summary ?? project.idea, 130)}
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-1.5">
                    {project.tags.slice(0, 3).map((tag) => (
                      <Badge key={tag} tone="muted">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                  <p className="mt-3 border-t border-edge pt-3 text-xs text-content-subtle">
                    {relativeTime(project.created_at)}
                  </p>
                </Card>
              </Link>
            ))}
          </div>

          {pageCount > 1 ? (
            <nav
              className="mt-6 flex items-center justify-between"
              aria-label="Project pagination"
            >
              <Button
                variant="secondary"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((current) => Math.max(0, current - 1))}
              >
                Previous
              </Button>
              <span className="text-xs text-content-muted">
                Page {page + 1} of {pageCount}
              </span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page + 1 >= pageCount}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
              </Button>
            </nav>
          ) : null}
        </>
      )}
    </div>
  );
}
