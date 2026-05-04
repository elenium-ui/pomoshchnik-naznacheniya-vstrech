export type ModeName = "client" | "admin";

export type AuthSessionResponse = {
  user: {
    telegram_user_id: number;
    first_name: string | null;
    last_name: string | null;
    username: string | null;
  };
  access: {
    is_admin: boolean;
    available_modes: ModeName[];
    default_mode: ModeName;
    current_mode: ModeName;
  };
};

