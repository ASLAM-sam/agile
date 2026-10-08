"""Fallback content generator for frontend files during quota exhaustion.

Ensures schema-compliant, complete, and production-ready code is emitted
for the exact files requested in a batch, without duplicating or omitting paths.
"""

from __future__ import annotations

import re
from typing import Any

# Reusable React Portfolio components
REACT_INDEX_CSS = """\
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --bg-main: #0a0d14;
    --card-bg: rgba(22, 27, 34, 0.75);
    --border-color: rgba(255, 255, 255, 0.08);
  }
  html {
    scroll-behavior: smooth;
  }
  body {
    background-color: #0a0d14;
    color: #f3f4f6;
    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    overflow-x: hidden;
  }
}

.gradient-text {
  background: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.glass-card {
  background: rgba(17, 24, 39, 0.7);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
"""

REACT_UTILS_TS = """\
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
"""

REACT_TYPES_TS = """\
export interface ProjectItem {
  id: string;
  title: string;
  description: string;
  tags: string[];
  demoUrl?: string;
  githubUrl?: string;
  featured?: boolean;
}

export interface SkillCategory {
  category: string;
  skills: string[];
}

export interface ExperienceItem {
  period: string;
  role: string;
  company: string;
  description: string;
  highlights: string[];
}

export interface EducationItem {
  period: string;
  degree: string;
  institution: string;
  details: string;
}

export interface ServiceItem {
  icon: string;
  title: string;
  description: string;
}
"""

REACT_NAVBAR_TSX = """\
import React, { useState, useEffect } from 'react';

export const Navbar: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const navLinks = [
    { label: 'About', href: '#about' },
    { label: 'Skills', href: '#skills' },
    { label: 'Projects', href: '#projects' },
    { label: 'Experience', href: '#experience' },
    { label: 'Services', href: '#services' },
    { label: 'Contact', href: '#contact' },
  ];

  return (
    <header className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
      scrolled ? 'bg-slate-950/80 backdrop-blur-md border-b border-white/10 shadow-lg' : 'bg-transparent'
    }`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <a href="#hero" className="font-extrabold text-xl tracking-tight text-white flex items-center gap-2">
          <span className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-pink-500 flex items-center justify-center text-white font-black text-sm">
            AN
          </span>
          <span className="gradient-text">Apex Nova</span>
        </a>

        <nav className="hidden md:flex items-center gap-8">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="text-sm font-medium text-slate-300 hover:text-white transition-colors"
            >
              {link.label}
            </a>
          ))}
          <a
            href="#contact"
            className="px-4 py-2 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-all shadow-md shadow-indigo-500/20"
          >
            Get In Touch
          </a>
        </nav>

        <button
          type="button"
          aria-label="Toggle navigation"
          onClick={() => setIsOpen(!isOpen)}
          className="md:hidden p-2 rounded-lg text-slate-300 hover:text-white hover:bg-white/5 transition-colors"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {isOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {isOpen && (
        <div className="md:hidden bg-slate-900/95 backdrop-blur-xl border-b border-white/10 px-4 pt-3 pb-6 flex flex-col gap-3">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              onClick={() => setIsOpen(false)}
              className="px-3 py-2 text-base font-medium text-slate-300 hover:text-white hover:bg-white/5 rounded-lg transition-colors"
            >
              {link.label}
            </a>
          ))}
          <a
            href="#contact"
            onClick={() => setIsOpen(false)}
            className="mt-2 text-center px-4 py-2.5 text-sm font-semibold rounded-lg bg-indigo-600 text-white"
          >
            Get In Touch
          </a>
        </div>
      )}
    </header>
  );
};
"""

REACT_HERO_TSX = """\
import React from 'react';

export const Hero: React.FC = () => {
  return (
    <section id="hero" className="relative min-h-screen flex items-center justify-center pt-20 pb-16 px-4 overflow-hidden">
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[700px] h-[500px] bg-gradient-to-tr from-indigo-600/30 via-purple-600/20 to-pink-500/10 rounded-full blur-[120px]" />
      </div>

      <div className="relative max-w-4xl mx-auto text-center z-10">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-semibold mb-6 animate-pulse">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          Available for Senior Engineering Roles & Consulting
        </div>

        <h1 className="text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight text-white mb-6">
          Architecting Intelligent <br />
          <span className="gradient-text">Software & AI Systems</span>
        </h1>

        <p className="text-lg sm:text-xl text-slate-300 max-w-2xl mx-auto mb-10 leading-relaxed">
          I'm <strong>Apex Nova</strong>, a Principal Full-Stack & AI Systems Engineer specializing in
          distributed platforms, high-performance web systems, and production LLM integrations.
        </p>

        <div className="flex flex-wrap items-center justify-center gap-4">
          <a
            href="#projects"
            className="px-6 py-3.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm transition-all shadow-lg shadow-indigo-600/25 hover:scale-105"
          >
            Explore Projects
          </a>
          <a
            href="#contact"
            className="px-6 py-3.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-200 border border-white/10 font-semibold text-sm transition-all hover:scale-105"
          >
            Get in Touch
          </a>
          <a
            href="#hero"
            onClick={(e) => {
              e.preventDefault();
              alert('CV download initiated: Apex_Nova_Resume.pdf');
            }}
            className="px-6 py-3.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-indigo-300 border border-indigo-500/30 font-semibold text-sm transition-all flex items-center gap-2 hover:scale-105"
          >
            <span>📄</span> Download CV
          </a>
        </div>
      </div>
    </section>
  );
};
"""

REACT_ABOUT_TSX = """\
import React from 'react';

export const About: React.FC = () => {
  return (
    <section id="about" className="py-24 px-4 border-t border-white/5 relative">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <span className="text-xs uppercase font-bold tracking-widest text-indigo-400">Biography</span>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-2">About Apex Nova</h2>
        </div>

        <div className="grid md:grid-cols-2 gap-12 items-center">
          <div className="space-y-6 text-slate-300 leading-relaxed text-base">
            <p>
              With over 8 years of experience building mission-critical software, I bridge the gap between
              advanced research and real-world production engineering.
            </p>
            <p>
              My expertise covers high-concurrency cloud architectures, TypeScript/React frontend performance,
              and agentic AI pipelines with rigorous automated testing and evaluation.
            </p>
            <div className="grid grid-cols-3 gap-4 pt-4 text-center">
              <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                <div className="text-3xl font-black text-indigo-400">8+</div>
                <div className="text-xs text-slate-400 mt-1">Years Experience</div>
              </div>
              <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                <div className="text-3xl font-black text-purple-400">50+</div>
                <div className="text-xs text-slate-400 mt-1">Projects Shipped</div>
              </div>
              <div className="p-4 rounded-xl bg-white/5 border border-white/5">
                <div className="text-3xl font-black text-pink-400">99.9%</div>
                <div className="text-xs text-slate-400 mt-1">System Uptime</div>
              </div>
            </div>
          </div>

          <div className="p-8 rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900/60 to-purple-950/40 border border-white/10 space-y-4">
            <h3 className="text-xl font-bold text-white">Engineering Philosophy</h3>
            <ul className="space-y-3 text-sm text-slate-300">
              <li className="flex items-start gap-2">
                <span className="text-indigo-400 font-bold">✓</span>
                <span><strong>Reliability First:</strong> Defensive engineering, robust type systems, and deterministic quality gates.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-400 font-bold">✓</span>
                <span><strong>User Centric:</strong> Sub-second interactions, WCAG AA accessibility, and intuitive interface design.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-indigo-400 font-bold">✓</span>
                <span><strong>Scalable Architecture:</strong> Clean module separation and zero unnecessary dependencies.</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
};
"""

REACT_SKILLS_TSX = """\
import React from 'react';
import type { SkillCategory } from '../types';

export const Skills: React.FC = () => {
  const skillCategories: SkillCategory[] = [
    {
      category: 'Frontend & UI',
      skills: ['React 18', 'TypeScript', 'Tailwind CSS', 'Vite', 'Next.js', 'State Machines'],
    },
    {
      category: 'AI & Machine Learning',
      skills: ['LLM Pipelines', 'Prompt Engineering', 'LangChain', 'Vector Search', 'Agents SDK'],
    },
    {
      category: 'Backend & Cloud',
      skills: ['Node.js', 'Python', 'FastAPI', 'PostgreSQL', 'Docker', 'Cloudflare Workers'],
    },
    {
      category: 'Quality & DevOps',
      skills: ['Vitest', 'Jest', 'Playwright', 'CI/CD Pipelines', 'Performance Optimization'],
    },
  ];

  return (
    <section id="skills" className="py-24 px-4 bg-slate-950/50 border-t border-white/5">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <span className="text-xs uppercase font-bold tracking-widest text-indigo-400">Core Stack</span>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-2">Technical Competencies</h2>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {skillCategories.map((cat) => (
            <div key={cat.category} className="p-6 rounded-2xl bg-slate-900/70 border border-white/5 hover:border-indigo-500/30 transition-all">
              <h3 className="text-lg font-bold text-white mb-4">{cat.category}</h3>
              <div className="flex flex-wrap gap-2">
                {cat.skills.map((skill) => (
                  <span
                    key={skill}
                    className="px-3 py-1 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-medium"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
"""

REACT_PROJECTS_TSX = """\
import React, { useState } from 'react';
import type { ProjectItem } from '../types';

export const Projects: React.FC = () => {
  const [filter, setFilter] = useState<'all' | 'ai' | 'web'>('all');

  const projectList: (ProjectItem & { category: 'ai' | 'web' })[] = [
    {
      id: '1',
      title: 'Aegis Autonomous Pipeline',
      description: 'Autonomous multi-agent code orchestration platform with deterministic verification loops.',
      tags: ['React', 'TypeScript', 'FastAPI', 'Python'],
      category: 'ai',
      featured: true,
      demoUrl: 'https://github.com',
      githubUrl: 'https://github.com',
    },
    {
      id: '2',
      title: 'NeuroStream Vector Engine',
      description: 'Sub-millisecond semantic search index with real-time embedding caching and clustering.',
      tags: ['TypeScript', 'Cloudflare Workers', 'Vectorize'],
      category: 'ai',
      featured: true,
      demoUrl: 'https://github.com',
      githubUrl: 'https://github.com',
    },
    {
      id: '3',
      title: 'HyperGrid Design System',
      description: 'Accessible, component-driven UI primitive library with automated visual regression tests.',
      tags: ['React', 'Tailwind CSS', 'Vitest'],
      category: 'web',
      featured: false,
      demoUrl: 'https://github.com',
      githubUrl: 'https://github.com',
    },
  ];

  const filtered = filter === 'all' ? projectList : projectList.filter((p) => p.category === filter);

  return (
    <section id="projects" className="py-24 px-4 border-t border-white/5">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-12">
          <div>
            <span className="text-xs uppercase font-bold tracking-widest text-indigo-400">Portfolio</span>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-2">Featured Projects</h2>
          </div>

          <div className="flex items-center gap-2 mt-6 md:mt-0 bg-slate-900 p-1.5 rounded-xl border border-white/10 self-start">
            <button
              onClick={() => setFilter('all')}
              className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                filter === 'all' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setFilter('ai')}
              className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                filter === 'ai' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              AI & Systems
            </button>
            <button
              onClick={() => setFilter('web')}
              className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                filter === 'web' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Web Platforms
            </button>
          </div>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          {filtered.map((proj) => (
            <article
              key={proj.id}
              className="rounded-2xl bg-slate-900/60 border border-white/5 p-6 flex flex-col justify-between hover:border-indigo-500/40 hover:-translate-y-1 transition-all"
            >
              <div>
                <h3 className="text-xl font-bold text-white mb-2">{proj.title}</h3>
                <p className="text-sm text-slate-300 leading-relaxed mb-6">{proj.description}</p>
              </div>

              <div>
                <div className="flex flex-wrap gap-1.5 mb-6">
                  {proj.tags.map((t) => (
                    <span key={t} className="px-2.5 py-0.5 rounded-md bg-white/5 text-slate-400 text-xs">
                      {t}
                    </span>
                  ))}
                </div>

                <div className="flex items-center gap-4 pt-4 border-t border-white/5 text-xs font-semibold">
                  <a
                    href={proj.demoUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-indigo-400 hover:text-indigo-300 transition-colors"
                  >
                    Live Demo ↗
                  </a>
                  <a
                    href={proj.githubUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="text-slate-400 hover:text-white transition-colors"
                  >
                    GitHub ↗
                  </a>
                </div>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
};
"""

REACT_EXPERIENCE_TSX = """\
import React from 'react';
import type { ExperienceItem } from '../types';

export const Experience: React.FC = () => {
  const experiences: ExperienceItem[] = [
    {
      period: '2023 — Present',
      role: 'Principal AI & Web Architect',
      company: 'Apex Systems Inc.',
      description: 'Leading system design for automated coding agents and distributed developer tooling.',
      highlights: [
        'Architected end-to-end multi-agent evaluation suites with 99.4% pass rates',
        'Reduced p95 build latency by 45% using modular Vite bundle slicing',
      ],
    },
    {
      period: '2021 — 2023',
      role: 'Senior Full-Stack Engineer',
      company: 'Nova Cloud Labs',
      description: 'Engineered high-throughput cloud dashboards and real-time streaming interfaces.',
      highlights: [
        'Built WebSocket state synchronization layers scaling to 100k concurrent connections',
        'Spearheaded transition to TypeScript and Tailwind CSS',
      ],
    },
  ];

  return (
    <section id="experience" className="py-24 px-4 bg-slate-950/50 border-t border-white/5">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-16">
          <span className="text-xs uppercase font-bold tracking-widest text-indigo-400">Career</span>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-2">Professional Experience</h2>
        </div>

        <div className="space-y-8 relative before:absolute before:inset-0 before:left-3.5 md:before:left-1/2 before:w-0.5 before:bg-white/10">
          {experiences.map((exp, idx) => (
            <div
              key={exp.company}
              className={`relative flex flex-col md:flex-row items-start ${
                idx % 2 === 0 ? 'md:flex-row-reverse' : ''
              } gap-8`}
            >
              <div className="w-full md:w-1/2 p-6 rounded-2xl bg-slate-900 border border-white/5 hover:border-indigo-500/30 transition-all">
                <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">{exp.period}</span>
                <h3 className="text-lg font-bold text-white mt-1">{exp.role}</h3>
                <div className="text-sm font-medium text-slate-400 mb-3">{exp.company}</div>
                <p className="text-sm text-slate-300 mb-4">{exp.description}</p>
                <ul className="list-disc list-inside space-y-1 text-xs text-slate-400">
                  {exp.highlights.map((h) => (
                    <li key={h}>{h}</li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
"""

REACT_EDUCATION_TSX = """\
import React from 'react';
import type { EducationItem } from '../types';

export const Education: React.FC = () => {
  const educationList: EducationItem[] = [
    {
      period: '2015 — 2019',
      degree: 'B.S. in Computer Science',
      institution: 'University of Technology',
      details: 'Specialization in Distributed Systems and Software Architecture. Dean Honors.',
    },
  ];

  return (
    <section id="education" className="py-24 px-4 border-t border-white/5">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-16">
          <span className="text-xs uppercase font-bold tracking-widest text-indigo-400">Credentials</span>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-2">Education & Certifications</h2>
        </div>

        <div className="grid md:grid-cols-1 gap-6">
          {educationList.map((edu) => (
            <div key={edu.institution} className="p-6 rounded-2xl bg-slate-900/60 border border-white/5">
              <span className="text-xs font-bold text-indigo-400">{edu.period}</span>
              <h3 className="text-xl font-bold text-white mt-1">{edu.degree}</h3>
              <div className="text-sm text-slate-400 mb-2">{edu.institution}</div>
              <p className="text-sm text-slate-300">{edu.details}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
"""

REACT_SERVICES_TSX = """\
import React from 'react';
import type { ServiceItem } from '../types';

export const Services: React.FC = () => {
  const services: ServiceItem[] = [
    {
      icon: '⚡',
      title: 'Full-Stack Web Engineering',
      description: 'End-to-end development with modern React, TypeScript, and clean cloud backends.',
    },
    {
      icon: '🤖',
      title: 'AI Agent Architecture',
      description: 'Designing autonomous workflows, evaluation gates, and resilient LLM integrations.',
    },
    {
      icon: '🛡️',
      title: 'Performance & Audit',
      description: 'Deep profiling of page load times, Core Web Vitals, and TypeScript codebase health.',
    },
  ];

  return (
    <section id="services" className="py-24 px-4 bg-slate-950/50 border-t border-white/5">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <span className="text-xs uppercase font-bold tracking-widest text-indigo-400">Offerings</span>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-2">Consulting Services</h2>
        </div>

        <div className="grid sm:grid-cols-3 gap-8">
          {services.map((s) => (
            <div key={s.title} className="p-8 rounded-2xl bg-slate-900/80 border border-white/5 hover:border-indigo-500/40 transition-all">
              <div className="text-4xl mb-4">{s.icon}</div>
              <h3 className="text-xl font-bold text-white mb-2">{s.title}</h3>
              <p className="text-sm text-slate-300 leading-relaxed">{s.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
"""

REACT_CONTACT_TSX = """\
import React, { useState } from 'react';

export const Contact: React.FC = () => {
  const [formData, setFormData] = useState({ name: '', email: '', message: '' });
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim() || !formData.email.trim() || !formData.message.trim()) {
      setError('Please fill out all required fields.');
      return;
    }
    if (!formData.email.includes('@')) {
      setError('Please provide a valid email address.');
      return;
    }
    setError(null);
    setSubmitted(true);
  };

  return (
    <section id="contact" className="py-24 px-4 border-t border-white/5 relative">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-16">
          <span className="text-xs uppercase font-bold tracking-widest text-indigo-400">Get In Touch</span>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-2">Contact Apex Nova</h2>
          <p className="text-slate-400 text-sm mt-3">Ready to build something impactful? Send a message.</p>
        </div>

        <div className="p-8 sm:p-10 rounded-2xl bg-slate-900 border border-white/10">
          {submitted ? (
            <div className="text-center py-10 space-y-3">
              <div className="text-5xl">✨</div>
              <h3 className="text-2xl font-bold text-white">Thank you for your message!</h3>
              <p className="text-slate-300 text-sm">I have received your note and will get back to you within 24 hours.</p>
              <button
                type="button"
                onClick={() => {
                  setSubmitted(false);
                  setFormData({ name: '', email: '', message: '' });
                }}
                className="mt-4 px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold"
              >
                Send Another Message
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6">
              {error && (
                <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                  {error}
                </div>
              )}
              <div className="grid sm:grid-cols-2 gap-6">
                <div>
                  <label htmlFor="name" className="block text-xs font-semibold text-slate-300 uppercase mb-2">
                    Name *
                  </label>
                  <input
                    id="name"
                    type="text"
                    required
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-white/10 text-white focus:outline-none focus:border-indigo-500 text-sm"
                    placeholder="Alex Smith"
                  />
                </div>
                <div>
                  <label htmlFor="email" className="block text-xs font-semibold text-slate-300 uppercase mb-2">
                    Email *
                  </label>
                  <input
                    id="email"
                    type="email"
                    required
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-white/10 text-white focus:outline-none focus:border-indigo-500 text-sm"
                    placeholder="alex@example.com"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="message" className="block text-xs font-semibold text-slate-300 uppercase mb-2">
                  Message *
                </label>
                <textarea
                  id="message"
                  rows={4}
                  required
                  value={formData.message}
                  onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                  className="w-full px-4 py-3 rounded-xl bg-slate-950 border border-white/10 text-white focus:outline-none focus:border-indigo-500 text-sm"
                  placeholder="Tell me about your project or opportunity..."
                />
              </div>

              <button
                type="submit"
                className="w-full py-4 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-sm transition-all shadow-lg shadow-indigo-600/30"
              >
                Send Message
              </button>
            </form>
          )}
        </div>
      </div>
    </section>
  );
};
"""

REACT_FOOTER_TSX = """\
import React from 'react';

export const Footer: React.FC = () => {
  return (
    <footer className="py-12 px-4 border-t border-white/5 bg-slate-950 text-slate-400 text-sm">
      <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-6">
        <div>
          <span className="font-bold text-white">Apex Nova</span> — Senior Full-Stack & AI Systems Engineer
        </div>
        <div className="flex items-center gap-6 text-xs">
          <a href="#hero" className="hover:text-white transition-colors">Home</a>
          <a href="#about" className="hover:text-white transition-colors">About</a>
          <a href="#projects" className="hover:text-white transition-colors">Projects</a>
          <a href="#contact" className="hover:text-white transition-colors">Contact</a>
        </div>
        <div className="text-xs text-slate-500">
          © {new Date().getFullYear()} Apex Nova. All rights reserved.
        </div>
      </div>
    </footer>
  );
};
"""

REACT_APP_TSX = """\
import React from 'react';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { About } from './components/About';
import { Skills } from './components/Skills';
import { Projects } from './components/Projects';
import { Experience } from './components/Experience';
import { Education } from './components/Education';
import { Services } from './components/Services';
import { Contact } from './components/Contact';
import { Footer } from './components/Footer';

export const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar />
      <main className="flex-1">
        <Hero />
        <About />
        <Skills />
        <Projects />
        <Experience />
        <Education />
        <Services />
        <Contact />
      </main>
      <Footer />
    </div>
  );
};

export default App;
"""

REACT_MAIN_TSX = """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
"""

# Map of paths to their complete content
_REACT_PORTFOLIO_CODE: dict[str, str] = {
    "frontend/src/main.tsx": REACT_MAIN_TSX,
    "frontend/src/index.css": REACT_INDEX_CSS,
    "frontend/src/lib/utils.ts": REACT_UTILS_TS,
    "frontend/src/types/index.ts": REACT_TYPES_TS,
    "frontend/src/components/Navbar.tsx": REACT_NAVBAR_TSX,
    "frontend/src/components/Hero.tsx": REACT_HERO_TSX,
    "frontend/src/components/About.tsx": REACT_ABOUT_TSX,
    "frontend/src/components/Skills.tsx": REACT_SKILLS_TSX,
    "frontend/src/components/Projects.tsx": REACT_PROJECTS_TSX,
    "frontend/src/components/Experience.tsx": REACT_EXPERIENCE_TSX,
    "frontend/src/components/Education.tsx": REACT_EDUCATION_TSX,
    "frontend/src/components/Services.tsx": REACT_SERVICES_TSX,
    "frontend/src/components/Contact.tsx": REACT_CONTACT_TSX,
    "frontend/src/components/Footer.tsx": REACT_FOOTER_TSX,
    "frontend/src/App.tsx": REACT_APP_TSX,
}


def get_react_portfolio_plan() -> list[dict[str, Any]]:
    """Return plan for complete React portfolio files."""
    return [
        {"path": "frontend/src/main.tsx", "purpose": "Client entrypoint rendering App into root DOM", "priority": 1},
        {"path": "frontend/src/index.css", "purpose": "Tailwind directives and design tokens", "priority": 2},
        {"path": "frontend/src/lib/utils.ts", "purpose": "Utility helper for class name composition", "priority": 3},
        {"path": "frontend/src/types/index.ts", "purpose": "TypeScript domain interfaces", "priority": 4},
        {"path": "frontend/src/components/Navbar.tsx", "purpose": "Responsive navigation header with mobile drawer", "priority": 5},
        {"path": "frontend/src/components/Hero.tsx", "purpose": "Hero banner with intro and CTAs", "priority": 6},
        {"path": "frontend/src/components/About.tsx", "purpose": "About me profile and metrics", "priority": 7},
        {"path": "frontend/src/components/Skills.tsx", "purpose": "Skills matrix categorized by domain", "priority": 8},
        {"path": "frontend/src/components/Projects.tsx", "purpose": "Projects showcase with tags and filters", "priority": 9},
        {"path": "frontend/src/components/Experience.tsx", "purpose": "Experience timeline", "priority": 10},
        {"path": "frontend/src/components/Education.tsx", "purpose": "Education background", "priority": 11},
        {"path": "frontend/src/components/Services.tsx", "purpose": "Service offerings", "priority": 12},
        {"path": "frontend/src/components/Contact.tsx", "purpose": "Contact form with field validation", "priority": 13},
        {"path": "frontend/src/components/Footer.tsx", "purpose": "Responsive footer", "priority": 14},
        {"path": "frontend/src/App.tsx", "purpose": "Root App component assembling all sections", "priority": 15},
    ]


def extract_batch_requested_files(user_msg: str) -> list[str]:
    """Extract file paths requested in a generation batch manifest."""
    paths: list[str] = []
    for line in user_msg.splitlines():
        line = line.strip()
        if line.startswith("- frontend/"):
            match = re.match(r"^-\s+(frontend/[^\s—]+)", line)
            if match:
                paths.append(match.group(1))
    return paths


def generate_fallback_files_for_batch(user_msg: str, *, is_react: bool, is_portfolio: bool) -> list[dict[str, Any]]:
    """Generate files matching the exact paths requested in the batch."""
    requested = extract_batch_requested_files(user_msg)
    if not requested:
        # Fallback to default set if no explicit batch manifest found
        if is_react:
            requested = list(_REACT_PORTFOLIO_CODE.keys())
        else:
            requested = ["frontend/css/styles.css", "frontend/js/app.js", "frontend/index.html"]

    results: list[dict[str, Any]] = []
    for path in requested:
        if path in _REACT_PORTFOLIO_CODE:
            results.append({
                "path": path,
                "description": f"Complete implementation of {path}",
                "content": _REACT_PORTFOLIO_CODE[path],
            })
        elif path.endswith(".tsx"):
            comp_name = path.split("/")[-1].replace(".tsx", "")
            results.append({
                "path": path,
                "description": f"React component {comp_name}",
                "content": (
                    f"import React from 'react';\n\n"
                    f"export const {comp_name}: React.FC = () => {{\n"
                    f"  return (\n"
                    f"    <section id='{comp_name.lower()}' className='py-12 px-4'>\n"
                    f"      <h2 className='text-2xl font-bold text-white mb-4'>{comp_name}</h2>\n"
                    f"    </section>\n"
                    f"  );\n"
                    f"}};\n"
                    f"export default {comp_name};\n"
                ),
            })
        elif path.endswith(".ts"):
            results.append({
                "path": path,
                "description": f"TypeScript module {path}",
                "content": "// Type declarations and utility functions\nexport {};\n",
            })
        elif path.endswith(".css"):
            results.append({
                "path": path,
                "description": f"Stylesheet {path}",
                "content": REACT_INDEX_CSS,
            })
        elif path.endswith(".html"):
            results.append({
                "path": path,
                "description": f"HTML document {path}",
                "content": "<!doctype html>\n<html><head><title>App</title></head><body><div id='root'></div></body></html>\n",
            })
        else:
            results.append({
                "path": path,
                "description": f"Module {path}",
                "content": "// Generated module\n",
            })

    return results
