#pragma once
#include "rednose/helpers/ekf.h"
extern "C" {
void car_update_25(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_24(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_30(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_26(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_27(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_29(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_28(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_update_31(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea);
void car_err_fun(double *nom_x, double *delta_x, double *out_3684763726455908402);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_6002638304903196221);
void car_H_mod_fun(double *state, double *out_5652660698460706897);
void car_f_fun(double *state, double dt, double *out_3663302706887353644);
void car_F_fun(double *state, double dt, double *out_1384129804139994096);
void car_h_25(double *state, double *unused, double *out_8349894035894583173);
void car_H_25(double *state, double *unused, double *out_2129680048471215220);
void car_h_24(double *state, double *unused, double *out_3282884035066992982);
void car_H_24(double *state, double *unused, double *out_6876189375437724254);
void car_h_30(double *state, double *unused, double *out_5998546739535596579);
void car_H_30(double *state, double *unused, double *out_4787010293020401535);
void car_h_26(double *state, double *unused, double *out_996873471874750934);
void car_H_26(double *state, double *unused, double *out_5871183367345271444);
void car_h_27(double *state, double *unused, double *out_675688840162758456);
void car_H_27(double *state, double *unused, double *out_2612246981219976624);
void car_h_29(double *state, double *unused, double *out_400494777878252567);
void car_H_29(double *state, double *unused, double *out_5297241637334793719);
void car_h_28(double *state, double *unused, double *out_6116554133468973323);
void car_H_28(double *state, double *unused, double *out_4183514762719104983);
void car_h_31(double *state, double *unused, double *out_8625088098179089062);
void car_H_31(double *state, double *unused, double *out_2099034086594254792);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}