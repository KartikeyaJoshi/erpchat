import { useCallback, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import ThemeToggle from '../components/ThemeToggle'
import './LandingPage.css'

const SECTION_SCROLL_THRESHOLD = 120

function getSectionScrollTop(sectionId) {
  const el = document.getElementById(sectionId)
  if (!el) return null
  const nav = document.querySelector('.landing-nav')
  const offset = (nav?.offsetHeight ?? 72) + 20
  return el.getBoundingClientRect().top + window.scrollY - offset
}

function scrollToSection(sectionId, { smooth = true } = {}) {
  const targetTop = getSectionScrollTop(sectionId)
  if (targetTop == null) return

  const distance = Math.abs(window.scrollY - targetTop)
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const behavior =
    smooth && distance > SECTION_SCROLL_THRESHOLD && !prefersReducedMotion
      ? 'smooth'
      : 'auto'

  window.scrollTo({ top: targetTop, behavior })
  history.replaceState(null, '', `#${sectionId}`)
}

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  visible: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.55, delay: i * 0.1, ease: [0.22, 1, 0.36, 1] },
  }),
}

const stagger = {
  visible: { transition: { staggerChildren: 0.1 } },
}

const FEATURES = [
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M8 10h8M8 14h5M6 4h12a2 2 0 012 2v14l-4-2-4 2-4-2-4 2V6a2 2 0 012-2z"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
    title: 'Natural Language Queries',
    description:
      'Ask demo business questions in plain English — see how NL maps to SQL over a fixed sample schema.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M4 19V5a1 1 0 011-1h14a1 1 0 011 1v14M8 17v-4M12 17V9M16 17v-6"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
      </svg>
    ),
    title: 'Multi-Module Demo',
    description:
      'Explore a sample ERP spanning finance, HR, inventory, and sales — all wired to one read-only schema.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M12 3l7 4v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V7l7-4z"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinejoin="round"
        />
        <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    title: 'Visible Schema',
    description:
      'Browse every table, column, and join path in the demo schema panel — no uploads, no connectors.',
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden>
        <path
          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
        <path d="M9 14h6M9 18h4" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
      </svg>
    ),
    title: 'Smart Disambiguation',
    description:
      'When multiple sample records match, the analyst asks you to pick — mirroring real ERP ambiguity.',
  },
]

const STATS = [
  { value: '12', label: 'Demo Tables' },
  { value: '5', label: 'ERP Modules' },
  { value: 'Fixed', label: 'Schema' },
  { value: 'NL→SQL', label: 'Pipeline' },
]

const STEPS = [
  { step: '01', title: 'Browse live schema', text: 'Inspect tables, columns, relationships, and sample rows from the database.' },
  { step: '02', title: 'Ask a question', text: 'Type a business query — the agent maps it to the live ERP tables.' },
  { step: '03', title: 'See the answer', text: 'Get insights grounded in real rows from your connected database.' },
]

function LogoIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 19V5a1 1 0 011-1h14a1 1 0 011 1v14M8 17v-4M12 17V9M16 17v-6"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  )
}

export default function LandingPage() {
  const location = useLocation()

  useEffect(() => {
    if (!location.hash) return
    const sectionId = location.hash.replace('#', '')
    requestAnimationFrame(() => scrollToSection(sectionId, { smooth: false }))
  }, [location.pathname, location.hash])

  const onSectionNav = useCallback((event, sectionId) => {
    event.preventDefault()
    scrollToSection(sectionId)
  }, [])

  return (
    <div className="landing">
      <div className="landing-bg" aria-hidden>
        <div className="landing-gradient-orb landing-gradient-orb--1" />
        <div className="landing-gradient-orb landing-gradient-orb--2" />
        <div className="landing-gradient-orb landing-gradient-orb--3" />
        <div className="landing-grid" />
      </div>

      <motion.nav
        className="landing-nav"
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="landing-nav-brand">
          <div className="landing-logo">
            <LogoIcon />
          </div>
          <span className="landing-nav-title">ERPChat</span>
        </div>
        <div className="landing-nav-actions">
          <Link to="/schema" className="landing-nav-link">Schema</Link>
          <a
            href="#features"
            className="landing-nav-link"
            onClick={(e) => onSectionNav(e, 'features')}
          >
            Features
          </a>
          <ThemeToggle />
          <Link to="/chat" className="landing-btn landing-btn--primary landing-btn--sm">
            Try Now
          </Link>
        </div>
      </motion.nav>

      <section className="landing-hero">
        <motion.div
          className="landing-hero-content"
          initial="hidden"
          animate="visible"
          variants={stagger}
        >
          <motion.div className="landing-badge" variants={fadeUp} custom={0}>
            <span className="landing-badge-dot" />
            Interactive Prototype
          </motion.div>

          <motion.h1 className="landing-headline" variants={fadeUp} custom={1}>
            See how an ERP analyst{' '}
            <span className="landing-headline-gradient">answers in plain language</span>
          </motion.h1>

          <motion.p className="landing-subheadline" variants={fadeUp} custom={2}>
            ERPChat is a working prototype — explore the live database schema, ask
            business questions, and get answers from real ERP tables.
          </motion.p>

          <motion.div className="landing-cta-group" variants={fadeUp} custom={3}>
            <Link to="/chat" className="landing-btn landing-btn--primary landing-btn--lg">
              <span>Try Now</span>
              <svg viewBox="0 0 24 24" fill="none" aria-hidden>
                <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
            <a
              href="#features"
              className="landing-btn landing-btn--ghost landing-btn--lg"
              onClick={(e) => onSectionNav(e, 'features')}
            >
              Explore features
            </a>
          </motion.div>

          <motion.div className="landing-stats" variants={fadeUp} custom={4}>
            {STATS.map((stat, i) => (
              <motion.div
                key={stat.label}
                className="landing-stat"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.6 + i * 0.08, duration: 0.4 }}
              >
                <span className="landing-stat-value">{stat.value}</span>
                <span className="landing-stat-label">{stat.label}</span>
              </motion.div>
            ))}
          </motion.div>
        </motion.div>

        <motion.div
          className="landing-hero-visual"
          initial={{ opacity: 0, x: 40, scale: 0.96 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          transition={{ duration: 0.7, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="landing-mockup">
            <div className="landing-mockup-bar">
              <span className="landing-mockup-dot landing-mockup-dot--red" />
              <span className="landing-mockup-dot landing-mockup-dot--yellow" />
              <span className="landing-mockup-dot landing-mockup-dot--green" />
              <span className="landing-mockup-title">ERPChat</span>
            </div>
            <div className="landing-mockup-body">
              <motion.div
                className="landing-mockup-msg landing-mockup-msg--user"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.8, duration: 0.4 }}
              >
                What is total revenue in 2026?
              </motion.div>
              <motion.div
                className="landing-mockup-msg landing-mockup-msg--ai"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 1.2, duration: 0.4 }}
              >
                <span className="landing-mockup-ai-label">ERP Analyst</span>
                Total revenue for FY 2026 is <strong>₹4.2 Cr</strong>, up 18% YoY across all business units.
              </motion.div>
              <motion.div
                className="landing-mockup-typing"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.6, duration: 0.3 }}
              >
                <span /><span /><span />
              </motion.div>
            </div>
          </div>
        </motion.div>
      </section>

      <section id="features" className="landing-section">
        <motion.div
          className="landing-section-header"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="landing-section-title">What this prototype shows</h2>
          <p className="landing-section-desc">
            A proof-of-concept for natural-language ERP analytics over a curated demo schema.
          </p>
        </motion.div>

        <div className="landing-features">
          {FEATURES.map((feature, i) => (
            <motion.article
              key={feature.title}
              className="landing-feature-card"
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.5, delay: i * 0.08 }}
              whileHover={{ y: -4, transition: { duration: 0.2 } }}
            >
              <div className="landing-feature-icon">{feature.icon}</div>
              <h3 className="landing-feature-title">{feature.title}</h3>
              <p className="landing-feature-desc">{feature.description}</p>
            </motion.article>
          ))}
        </div>
      </section>

      <section id="how-it-works" className="landing-section landing-section--alt">
        <motion.div
          className="landing-section-header"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-80px' }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="landing-section-title">How it works</h2>
          <p className="landing-section-desc">
            From question to insight in three simple steps.
          </p>
        </motion.div>

        <div className="landing-steps">
          {STEPS.map((step, i) => (
            <motion.div
              key={step.step}
              className="landing-step"
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.5, delay: i * 0.12 }}
            >
              <span className="landing-step-num">{step.step}</span>
              <h3 className="landing-step-title">{step.title}</h3>
              <p className="landing-step-text">{step.text}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <motion.section
        className="landing-cta-banner"
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-80px' }}
        transition={{ duration: 0.5 }}
      >
        <div className="landing-cta-banner-inner">
          <h2 className="landing-cta-banner-title">Ready to try the demo?</h2>
          <p className="landing-cta-banner-text">
            Open the schema panel, pick a starter question, and see the analyst work over sample data.
          </p>
          <Link to="/chat" className="landing-btn landing-btn--white landing-btn--lg">
            <span>Try Now</span>
            <svg viewBox="0 0 24 24" fill="none" aria-hidden>
              <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        </div>
      </motion.section>

      <footer className="landing-footer">
        <div className="landing-footer-brand">
          <div className="landing-logo landing-logo--sm">
            <LogoIcon />
          </div>
          <span>ERPChat</span>
        </div>
        <p className="landing-footer-copy">
          Interactive prototype &mdash; sample ERP schema and seeded demo data.
        </p>
      </footer>
    </div>
  )
}
