import './style.css'

document.addEventListener('DOMContentLoaded', () => {
  initScrollAnimations()
  initDemoAnimation()
  initLegendInteraction()
  initSmoothScroll()
  initTechGridAnimation()
})

function initScrollAnimations() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible')
      }
    })
  }, { root: null, rootMargin: '0px 0px -100px 0px', threshold: 0.1 })

  document.querySelectorAll('.section-header, .feature-card, .demo-panel, .tech-stack, .architecture-placeholder').forEach(el => {
    el.classList.add('fade-in-up')
    observer.observe(el)
  })

  const featuresGrid = document.querySelector('.features-grid')
  if (featuresGrid) {
    featuresGrid.classList.add('stagger-children')
    observer.observe(featuresGrid)
  }
}

function initDemoAnimation() {
  const piiElements = document.querySelectorAll('.pii')
  const redactedElements = document.querySelectorAll('.redacted')
  const replayBtn = document.getElementById('demo-replay')
  let animationTimeout: number | null = null

  function runDemoAnimation() {
    piiElements.forEach(el => el.classList.remove('highlighted'))
    redactedElements.forEach(el => el.classList.remove('visible'))

    let delay = 500
    piiElements.forEach((pii) => {
      const piiEl = pii as HTMLElement
      const type = piiEl.dataset.type

      setTimeout(() => {
        piiEl.classList.add('highlighted')
        const allRedacted = document.querySelectorAll(`.demo-panel-redacted .redacted[data-type="${type}"]`)
        allRedacted.forEach((r, i) => {
          setTimeout(() => r.classList.add('visible'), i * 100)
        })
      }, delay)

      delay += 300
    })
  }

  const demoSection = document.getElementById('demo')
  if (demoSection) {
    const demoObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          if (animationTimeout) clearTimeout(animationTimeout)
          animationTimeout = window.setTimeout(runDemoAnimation, 500)
          demoObserver.unobserve(entry.target)
        }
      })
    }, { threshold: 0.3 })
    demoObserver.observe(demoSection)
  }

  if (replayBtn) {
    replayBtn.addEventListener('click', runDemoAnimation)
  }
}

function initLegendInteraction() {
  document.querySelectorAll('.demo-legend-chip').forEach(chip => {
    chip.addEventListener('mouseenter', () => {
      const type = (chip as HTMLElement).dataset.type
      document.querySelectorAll(`.pii[data-type="${type}"]`).forEach(el => el.classList.add('highlighted'))
      document.querySelectorAll(`.redacted[data-type="${type}"]`).forEach(el => {
        (el as HTMLElement).style.boxShadow = '0 0 12px currentColor'
      })
      chip.classList.add('active')
    })

    chip.addEventListener('mouseleave', () => {
      const type = (chip as HTMLElement).dataset.type
      document.querySelectorAll(`.pii[data-type="${type}"]`).forEach(el => el.classList.remove('highlighted'))
      document.querySelectorAll(`.redacted[data-type="${type}"]`).forEach(el => {
        (el as HTMLElement).style.boxShadow = ''
      })
      chip.classList.remove('active')
    })
  })
}

function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', (e) => {
      e.preventDefault()
      const targetId = anchor.getAttribute('href')
      if (targetId && targetId !== '#') {
        document.querySelector(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    })
  })
}

function initTechGridAnimation() {
  const techNodes = document.querySelectorAll('.tech-node')
  const techGrid = document.querySelector('.tech-grid')

  if (techGrid) {
    const techObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          let delay = 0
          techNodes.forEach(node => {
            setTimeout(() => {
              (node as HTMLElement).style.opacity = '1'
              ;(node as HTMLElement).style.transform = 'translateY(0)'
            }, delay)
            delay += 80
          })
          techObserver.unobserve(entry.target)
        }
      })
    }, { threshold: 0.2 })

    techNodes.forEach(node => {
      ;(node as HTMLElement).style.opacity = '0'
      ;(node as HTMLElement).style.transform = 'translateY(20px)'
      ;(node as HTMLElement).style.transition = 'all 0.4s ease-out'
    })

    techObserver.observe(techGrid)
  }
}

const nav = document.querySelector('.nav') as HTMLElement
window.addEventListener('scroll', () => {
  if (nav) {
    nav.style.background = window.scrollY > 100
      ? 'rgba(7, 13, 24, 0.98)'
      : 'linear-gradient(to bottom, rgba(7, 13, 24, 0.95), rgba(7, 13, 24, 0.8))'
  }
})
