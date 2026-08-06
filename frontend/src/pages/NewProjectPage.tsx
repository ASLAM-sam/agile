import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '@/api/client';
import { projectApi } from '@/api/resources';
import { PageHeader } from '@/components/layout/PageHeader';
import { Button } from '@/components/ui/Button';
import { Card, CardBody } from '@/components/ui/Card';
import { Input, Textarea } from '@/components/ui/Input';

const EXAMPLES = [
  'A hospital management system for scheduling appointments, managing patient records and tracking staff rotas',
  'An inventory management system for a warehouse with stock levels, suppliers and low-stock alerts',
  'A personal portfolio website showcasing projects, skills and a contact form',
  'A restaurant ordering platform with a menu, cart, checkout and order tracking',
  'A learning management system with courses, lessons, quizzes and student progress',
];

const MIN_IDEA_LENGTH = 10;

export function NewProjectPage() {
  const navigate = useNavigate();

  const [idea, setIdea] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [isSubmitting, setSubmitting] = useState(false);

  const isTooShort = idea.trim().length > 0 && idea.trim().length < MIN_IDEA_LENGTH;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setProblems([]);
    setSubmitting(true);
    try {
      const project = await projectApi.create(idea.trim(), name.trim() || undefined);
      // Straight to the review screen: analysis is the next thing the user needs.
      navigate(`/projects/${project.id}`, { replace: true });
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(caught.message);
        setProblems(caught.validationProblems);
      } else {
        setError('The project could not be created. Please try again.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl animate-fade-in">
      <PageHeader
        title="New project"
        description="Describe what you want built. The Business Analyst will work out what it needs."
        breadcrumbs={[{ label: 'Projects', to: '/projects' }, { label: 'New' }]}
      />

      <Card>
        <CardBody className="space-y-5 p-6">
          <form onSubmit={handleSubmit} className="space-y-5" noValidate>
            {error ? (
              <div
                className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger"
                role="alert"
              >
                <p>{error}</p>
                {problems.length > 0 ? (
                  <ul className="mt-1.5 space-y-0.5 text-xs">
                    {problems.map((problem) => (
                      <li key={problem}>• {problem}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            <Textarea
              label="Your software idea"
              value={idea}
              onChange={(event) => setIdea(event.target.value)}
              placeholder="Build a hospital management system that lets receptionists book appointments, doctors view patient records, and administrators manage staff…"
              required
              rows={6}
              maxLength={4000}
              hint="Be specific about who uses it and what they need to do. More detail produces a better-targeted project."
              {...(isTooShort ? { error: `Use at least ${MIN_IDEA_LENGTH} characters.` } : {})}
            />

            <Input
              label="Project name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Leave blank to let the Manager name it"
              maxLength={200}
              hint="Optional. The Manager agent will choose a professional name if you leave this empty."
            />

            <div className="flex items-center justify-between gap-3 border-t border-edge pt-5">
              <span className="text-xs text-content-subtle">
                {idea.trim().length} / 4000 characters
              </span>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => navigate('/projects')}>
                  Cancel
                </Button>
                <Button
                  type="submit"
                  isLoading={isSubmitting}
                  disabled={idea.trim().length < MIN_IDEA_LENGTH}
                >
                  Create project
                </Button>
              </div>
            </div>
          </form>
        </CardBody>
      </Card>

      <section className="mt-6" aria-labelledby="examples-heading">
        <h2 id="examples-heading" className="mb-3 text-xs font-medium uppercase tracking-wide text-content-subtle">
          Need inspiration?
        </h2>
        <div className="space-y-2">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setIdea(example)}
              className="w-full rounded-lg border border-edge bg-surface-raised px-4 py-3 text-left text-sm text-content-muted transition-colors hover:border-brand-500/40 hover:text-content"
            >
              {example}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
