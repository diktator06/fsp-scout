export interface SearchableSkill {
  name: string;
  slug: string;
  aliases: string[];
}

export function normalizeSearch(value: string): string {
  // «Ё» и «е» в поиске не различаем: «ёмкость» и «емкость» — один запрос.
  return value.trim().toLowerCase().replaceAll('ё', 'е');
}

export function searchSkills<T extends SearchableSkill>(
  skills: readonly T[],
  query: string,
  limit = 30,
): T[] {
  // Совпадение ищется в названии, slug и синонимах («питон» → Python, «k8s» →
  // Kubernetes). Совпадения с начала слова идут первыми, внутри групп — по алфавиту.
  const needle = normalizeSearch(query);
  if (!needle) return [...skills].sort((a, b) => a.name.localeCompare(b.name)).slice(0, limit);

  const scored: Array<{ skill: T; rank: number }> = [];
  for (const skill of skills) {
    const haystacks = [skill.name, skill.slug, ...skill.aliases].map(normalizeSearch);
    if (haystacks.some((text) => text.startsWith(needle))) scored.push({ skill, rank: 0 });
    else if (haystacks.some((text) => text.includes(needle))) scored.push({ skill, rank: 1 });
  }
  return scored
    .sort((a, b) => a.rank - b.rank || a.skill.name.localeCompare(b.skill.name))
    .slice(0, limit)
    .map((item) => item.skill);
}
