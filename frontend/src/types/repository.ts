export interface Repository {
  id: number;
  github_url: string;
  owner: string;
  name: string;
  default_branch: string;
  first_analyzed_at: string | null;
  last_analyzed_at: string | null;
  analysis_count: number;
}
