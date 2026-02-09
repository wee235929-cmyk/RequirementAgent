import { useEffect, useRef } from 'react'

export default function StarryBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Set canvas size
    const resizeCanvas = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }
    resizeCanvas()
    window.addEventListener('resize', resizeCanvas)

    // Stars with movement
    interface Star {
      x: number
      y: number
      size: number
      opacity: number
      twinkleSpeed: number
      twinklePhase: number
      speedX: number
      speedY: number
    }

    const stars: Star[] = []
    const starCount = 200

    for (let i = 0; i < starCount; i++) {
      stars.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        size: Math.random() * 1.5 + 0.5,
        opacity: Math.random() * 0.5 + 0.3,
        twinkleSpeed: Math.random() * 0.02 + 0.01,
        twinklePhase: Math.random() * Math.PI * 2,
        speedX: (Math.random() - 0.5) * 0.15,
        speedY: (Math.random() - 0.5) * 0.15,
      })
    }

    // Shooting stars
    interface ShootingStar {
      x: number
      y: number
      length: number
      speed: number
      opacity: number
      active: boolean
      angle: number
    }

    const shootingStars: ShootingStar[] = []
    const maxShootingStars = 5

    const createShootingStar = () => {
      if (shootingStars.filter(s => s.active).length >= maxShootingStars) return
      
      shootingStars.push({
        x: Math.random() * canvas.width * 0.7,
        y: Math.random() * canvas.height * 0.4,
        length: Math.random() * 100 + 60,
        speed: Math.random() * 10 + 8,
        opacity: 1,
        active: true,
        angle: Math.PI / 4 + (Math.random() - 0.5) * 0.4,
      })
    }

    // More frequent shooting stars
    const shootingStarInterval = setInterval(() => {
      if (Math.random() < 0.5) {
        createShootingStar()
      }
    }, 800)

    let animationId: number

    const animate = () => {
      // Clear with slight fade for trail effect
      ctx.fillStyle = 'rgba(0, 0, 0, 0.15)'
      ctx.fillRect(0, 0, canvas.width, canvas.height)

      // Draw and move stars
      stars.forEach(star => {
        star.twinklePhase += star.twinkleSpeed
        const twinkle = Math.sin(star.twinklePhase) * 0.3 + 0.7
        
        // Move star slowly
        star.x += star.speedX
        star.y += star.speedY
        
        // Wrap around edges
        if (star.x < 0) star.x = canvas.width
        if (star.x > canvas.width) star.x = 0
        if (star.y < 0) star.y = canvas.height
        if (star.y > canvas.height) star.y = 0
        
        // Draw star with glow
        ctx.beginPath()
        ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(255, 255, 255, ${star.opacity * twinkle})`
        ctx.fill()
        
        // Add subtle glow for larger stars
        if (star.size > 1) {
          ctx.beginPath()
          ctx.arc(star.x, star.y, star.size * 2, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(255, 255, 255, ${star.opacity * twinkle * 0.1})`
          ctx.fill()
        }
      })

      // Draw and update shooting stars
      shootingStars.forEach((star, index) => {
        if (!star.active) return

        const tailX = star.x - Math.cos(star.angle) * star.length
        const tailY = star.y - Math.sin(star.angle) * star.length

        // Create gradient for shooting star
        const gradient = ctx.createLinearGradient(tailX, tailY, star.x, star.y)
        gradient.addColorStop(0, 'rgba(255, 255, 255, 0)')
        gradient.addColorStop(0.3, `rgba(200, 220, 255, ${star.opacity * 0.3})`)
        gradient.addColorStop(0.7, `rgba(255, 255, 255, ${star.opacity * 0.7})`)
        gradient.addColorStop(1, `rgba(255, 255, 255, ${star.opacity})`)

        ctx.beginPath()
        ctx.moveTo(tailX, tailY)
        ctx.lineTo(star.x, star.y)
        ctx.strokeStyle = gradient
        ctx.lineWidth = 2
        ctx.stroke()

        // Draw bright glowing head
        ctx.beginPath()
        ctx.arc(star.x, star.y, 3, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(255, 255, 255, ${star.opacity})`
        ctx.fill()
        
        // Outer glow
        ctx.beginPath()
        ctx.arc(star.x, star.y, 6, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(200, 220, 255, ${star.opacity * 0.3})`
        ctx.fill()

        // Update position
        star.x += Math.cos(star.angle) * star.speed
        star.y += Math.sin(star.angle) * star.speed
        star.opacity -= 0.006

        // Remove if out of bounds or faded
        if (star.x > canvas.width || star.y > canvas.height || star.opacity <= 0) {
          shootingStars.splice(index, 1)
        }
      })

      animationId = requestAnimationFrame(animate)
    }

    // Initial fill
    ctx.fillStyle = '#000'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    
    animate()

    return () => {
      window.removeEventListener('resize', resizeCanvas)
      clearInterval(shootingStarInterval)
      cancelAnimationFrame(animationId)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none"
      style={{ 
        background: 'linear-gradient(to bottom, #000000, #050510, #000000)',
        zIndex: 0
      }}
    />
  )
}
