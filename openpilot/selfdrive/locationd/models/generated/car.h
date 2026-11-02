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
void car_err_fun(double *nom_x, double *delta_x, double *out_4525121693915560921);
void car_inv_err_fun(double *nom_x, double *true_x, double *out_1972415448394742236);
void car_H_mod_fun(double *state, double *out_7275833948890819174);
void car_f_fun(double *state, double dt, double *out_7956715178949728761);
void car_F_fun(double *state, double dt, double *out_4817379664253254158);
void car_h_25(double *state, double *unused, double *out_147038242079145023);
void car_H_25(double *state, double *unused, double *out_8151142693229822154);
void car_h_24(double *state, double *unused, double *out_4380945631886811145);
void car_H_24(double *state, double *unused, double *out_6737675781677406326);
void car_h_30(double *state, double *unused, double *out_3784487770333167373);
void car_H_30(double *state, double *unused, double *out_7777268421972480835);
void car_h_26(double *state, double *unused, double *out_1858242100747789462);
void car_H_26(double *state, double *unused, double *out_4409639374355765930);
void car_h_27(double *state, double *unused, double *out_8970756540361744684);
void car_H_27(double *state, double *unused, double *out_8494712339936645870);
void car_h_29(double *state, double *unused, double *out_8786161037994013018);
void car_H_29(double *state, double *unused, double *out_7267037077658088651);
void car_h_28(double *state, double *unused, double *out_3833257662266850097);
void car_H_28(double *state, double *unused, double *out_6097307978981932391);
void car_h_31(double *state, double *unused, double *out_128155820205360866);
void car_H_31(double *state, double *unused, double *out_3783431272122414454);
void car_predict(double *in_x, double *in_P, double *in_Q, double dt);
void car_set_mass(double x);
void car_set_rotational_inertia(double x);
void car_set_center_to_front(double x);
void car_set_center_to_rear(double x);
void car_set_stiffness_front(double x);
void car_set_stiffness_rear(double x);
}