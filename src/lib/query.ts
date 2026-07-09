import { QueryClient } from "@tanstack/react-query";

export const LIVE_QUERY_OPTIONS = {
  staleTime: 30_000,
  gcTime: 10 * 60 * 1000,
  retry: 1,
  refetchOnWindowFocus: false,
  refetchOnReconnect: true,
  refetchOnMount: false,
  refetchIntervalInBackground: true,
  placeholderData: <T,>(previousData: T) => previousData,
} as const;

export const createAppQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        ...LIVE_QUERY_OPTIONS,
      },
      mutations: {
        retry: 0,
      },
    },
  });
