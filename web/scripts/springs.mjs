// Prints the two spring curves of tokens.css (DESIGN.md rule 9) as CSS linear() functions.
// A damped spring that starts at 0 and settles at 1. The damping ratio sets the overshoot; the stiffness is chosen
// so the motion is within 0.2 % of the target at the end of its duration. Run: node scripts/springs.mjs
const springs = [
  { name: "--spring-snappy", ms: 280, overshoot: 0.025 },
  { name: "--spring-soft", ms: 420, overshoot: 0.015 },
];

function curve({ ms, overshoot }) {
  // overshoot = exp(-zeta * pi / sqrt(1 - zeta^2))  ->  solve for zeta
  const l = -Math.log(overshoot) / Math.PI;
  const zeta = l / Math.sqrt(1 + l * l);
  const t1 = ms / 1000;
  const w = Math.log(1 / 0.002) / (zeta * t1); // envelope e^(-zeta w t) reaches 0.2 % at the end
  const wd = w * Math.sqrt(1 - zeta * zeta);
  const x = (t) => 1 - Math.exp(-zeta * w * t) * (Math.cos(wd * t) + ((zeta * w) / wd) * Math.sin(wd * t));
  const n = 24;
  const points = [];
  for (let i = 0; i <= n; i += 1) {
    const v = i === n ? 1 : x((i / n) * t1);
    points.push(Number(v.toFixed(3)));
  }
  const peak = Math.max(...points);
  return { zeta, points, peak };
}

for (const s of springs) {
  const { zeta, points, peak } = curve(s);
  console.log(`/* ${s.ms} ms, damping ratio ${zeta.toFixed(2)}, overshoot ${((peak - 1) * 100).toFixed(1)} % */`);
  console.log(`${s.name}: linear(${points.join(", ")});`);
}
